"""The worker's web3.py helpers for the XRPL EVM Treasury Wallet (#204).

No network: a real `Web3` sits on a fake provider that answers the JSON-RPC
calls these helpers make, so web3's own encoding and formatting still run.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
import rlp
from eth_abi import encode
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction
from remitx_worker import evm_service
from remitx_worker.evm_service import (
    from_base_units,
    get_native_balance,
    get_token_balance,
    get_web3,
    submit_transaction,
    to_base_units,
    wait_for_receipt,
)
from tests.evm_helpers import configure_fake_treasury
from web3 import Web3
from web3.providers.base import BaseProvider

CHAIN_ID = 1449000
TX_HASH = "0x" + "ab" * 32


class FakeProvider(BaseProvider):
    """Answers JSON-RPC from a dict of method -> result (or callable(params))."""

    def __init__(self, answers):
        super().__init__()
        self.answers = answers
        self.calls = []

    def make_request(self, method, params):
        self.calls.append((method, params))
        if method not in self.answers:
            raise AssertionError(f"unexpected RPC call {method}")
        answer = self.answers[method]
        result = answer(params) if callable(answer) else answer
        return {"jsonrpc": "2.0", "id": 1, "result": result}

    def methods(self):
        return [method for method, _ in self.calls]


def _fake_web3(**answers):
    provider = FakeProvider({"eth_chainId": hex(CHAIN_ID), **answers})
    return Web3(provider), provider


@pytest.fixture(autouse=True)
def _evm_settings(monkeypatch):
    for name in (
        "EVM_RPC_URL",
        "EVM_CHAIN_ID",
        "UCTUSD_EVM_CONTRACT_ADDRESS",
        "UCTUSD_EVM_DECIMALS",
    ):
        monkeypatch.delenv(name, raising=False)


# --- get_web3 ----------------------------------------------------------------


def _patch_provider(monkeypatch, chain_id):
    provider = FakeProvider({"eth_chainId": hex(chain_id)})
    seen = {}

    def http_provider(url, **kwargs):
        seen["url"] = url
        return provider

    monkeypatch.setattr(evm_service.Web3, "HTTPProvider", http_provider)
    return seen


def test_get_web3_accepts_the_configured_chain(monkeypatch):
    seen = _patch_provider(monkeypatch, CHAIN_ID)

    w3 = get_web3()

    assert w3.eth.chain_id == CHAIN_ID
    assert seen["url"] == "https://rpc.testnet.xrplevm.org"


def test_get_web3_rejects_a_different_chain(monkeypatch):
    monkeypatch.setenv("EVM_RPC_URL", "https://rpc.example/secret-api-key")
    _patch_provider(monkeypatch, 1)  # Ethereum mainnet

    with pytest.raises(RuntimeError, match="chain id 1, expected") as caught:
        get_web3()

    assert "secret-api-key" not in str(caught.value)


# --- base units ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "base_units"),
    [
        (Decimal("0"), 0),
        (Decimal("1"), 10**18),
        (Decimal("12.34"), 1234 * 10**16),
        (Decimal("0.000000000000000001"), 1),
        # 31 significant digits: past Decimal's default precision of 28.
        (Decimal("1234567890123.456789012345678901"), 1234567890123456789012345678901),
    ],
)
def test_base_units_round_trip_at_18_decimals(amount, base_units):
    assert to_base_units(amount) == base_units
    assert from_base_units(base_units) == amount


@pytest.mark.parametrize("amount", [1.5, 1, "1", None])
def test_to_base_units_rejects_anything_but_a_decimal(amount):
    with pytest.raises(TypeError):
        to_base_units(amount)


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("-1"),
        Decimal("-0.000000000000000001"),
        Decimal("0.0000000000000000001"),  # 19 places
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_to_base_units_rejects_bad_amounts(amount):
    with pytest.raises(ValueError):
        to_base_units(amount)


def test_to_base_units_follows_the_configured_decimals(monkeypatch):
    monkeypatch.setenv("UCTUSD_EVM_DECIMALS", "6")

    assert to_base_units(Decimal("1.5")) == 1_500_000
    assert from_base_units(1_500_000) == Decimal("1.5")
    with pytest.raises(ValueError, match="more than 6 decimal places"):
        to_base_units(Decimal("0.0000001"))


@pytest.mark.parametrize("value", [1.0, True, "1", Decimal("1")])
def test_from_base_units_rejects_anything_but_an_int(value):
    with pytest.raises(TypeError):
        from_base_units(value)


def test_from_base_units_rejects_negatives():
    with pytest.raises(ValueError):
        from_base_units(-1)


# --- balances ------------------------------------------------------------------


def test_get_token_balance_scales_by_decimals():
    holder = Account.create().address
    w3, provider = _fake_web3(
        eth_call=lambda params: "0x" + encode(["uint256"], [25 * 10**17]).hex()
    )

    assert get_token_balance(holder, w3=w3) == Decimal("2.5")

    (call,) = [params for method, params in provider.calls if method == "eth_call"]
    assert call[0]["to"].lower() == "0x7055071c7b79a859d9514e62833bff041ce71074"
    # balanceOf(address) selector, then the holder left-padded to 32 bytes.
    assert call[0]["data"].startswith("0x70a08231")
    assert call[0]["data"].endswith(holder[2:].lower())


def test_get_native_balance_reads_wei_as_xrp():
    w3, _ = _fake_web3(eth_getBalance=hex(3 * 10**17))

    assert get_native_balance(Account.create().address, w3=w3) == Decimal("0.3")


# --- wait_for_receipt -------------------------------------------------------------


def _waiting_web3(status):
    def wait(tx_hash, timeout):
        return {"transactionHash": tx_hash, "status": status}

    return SimpleNamespace(eth=SimpleNamespace(wait_for_transaction_receipt=wait))


def test_wait_for_receipt_returns_a_successful_receipt():
    receipt = wait_for_receipt(TX_HASH, w3=_waiting_web3(1))

    assert receipt["status"] == 1


def test_wait_for_receipt_raises_on_a_revert():
    with pytest.raises(RuntimeError, match="reverted"):
        wait_for_receipt(TX_HASH, w3=_waiting_web3(0))


# --- submit_transaction ---------------------------------------------------------


def test_submit_transaction_signs_as_the_treasury_and_does_not_wait(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    recipient = Account.create().address
    sent = []

    def send_raw(params):
        sent.append(params[0])
        return TX_HASH

    w3, provider = _fake_web3(
        eth_getTransactionCount=hex(7),
        eth_gasPrice=hex(785_000_000),
        eth_estimateGas=hex(52_000),
        eth_sendRawTransaction=send_raw,
    )

    tx_hash = submit_transaction({"to": recipient, "data": "0x1234"}, w3=w3)

    assert tx_hash == TX_HASH
    # Pending nonce, and nothing after the send: no receipt polling.
    nonce_calls = [
        list(params)
        for method, params in provider.calls
        if method == "eth_getTransactionCount"
    ]
    assert nonce_calls == [[treasury.address, "pending"]]
    assert provider.methods()[-1] == "eth_sendRawTransaction"
    assert "eth_getTransactionReceipt" not in provider.methods()

    (raw,) = sent
    assert Account.recover_transaction(raw) == treasury.address
    fields = _decode_legacy(raw)
    assert fields["nonce"] == 7
    assert fields["gasPrice"] == 785_000_000
    assert fields["gas"] == 52_000
    assert fields["to"].lower() == recipient.lower()
    assert fields["data"] == bytes.fromhex("1234")
    assert fields["chainId"] == CHAIN_ID

    calls = repr(provider.calls)
    for secret in treasury.secrets:
        assert secret not in calls


def _decode_legacy(raw):
    """Fields of a signed legacy (EIP-155) transaction."""
    payload = bytes.fromhex(raw[2:])
    # A typed transaction starts with a type byte < 0x7f; legacy is an RLP list.
    assert payload[0] >= 0xC0, "expected a legacy transaction"
    tx = rlp.decode(payload, Transaction)
    return {
        "nonce": tx.nonce,
        "gasPrice": tx.gasPrice,
        "gas": tx.gas,
        "to": "0x" + tx.to.hex(),
        "data": tx.data,
        "chainId": (tx.v - 35) // 2,
    }


def test_submit_transaction_rejects_caller_set_fees_and_nonces(monkeypatch):
    configure_fake_treasury(monkeypatch)
    w3, provider = _fake_web3()

    for field in ("nonce", "gasPrice", "maxFeePerGas", "chainId", "from", "gas"):
        with pytest.raises(ValueError, match="unsupported transaction fields"):
            submit_transaction({"to": Account.create().address, field: 1}, w3=w3)

    assert provider.calls == []
