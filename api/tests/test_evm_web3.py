"""The worker's web3.py helpers for the XRPL EVM Treasury Wallet (#221, #222).

No network: a real `Web3` sits on a fake provider that answers the JSON-RPC
calls these helpers make, so web3's own encoding and formatting still run.
"""

import logging
import re
import uuid
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest
import rlp
from eth_abi import encode
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction
from remitx_worker import evm_service
from remitx_worker.evm_service import (
    ERC20_ABI,
    TransactionRejected,
    burn_tokens,
    from_base_units,
    get_native_balance,
    get_token_balance,
    get_web3,
    send_transaction,
    submit_transaction,
    to_base_units,
    transaction_status,
    uuid_to_bytes32,
    wait_for_receipt,
)
from tests.evm_helpers import configure_fake_treasury
from web3 import Web3
from web3.exceptions import TimeExhausted, Web3RPCError
from web3.providers.base import BaseProvider

CHAIN_ID = 1449000
TX_HASH = "0x" + "ab" * 32
UCTUSD = "0x7055071c7b79a859d9514e62833bff041ce71074"


class RpcError:
    """An answer that is a JSON-RPC error response, not a result."""

    def __init__(self, message, code=-32000):
        self.message = message
        self.code = code


class FakeProvider(BaseProvider):
    """Answers JSON-RPC from a dict of method -> result (or callable(params)).
    An `RpcError` answer is sent back as a JSON-RPC error response."""

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
        if isinstance(result, RpcError):
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": result.code, "message": result.message},
            }
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
        "UCTUSD_CONTRACT_ADDRESS",
        "UCTUSD_EVM_DECIMALS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def send_lock(monkeypatch):
    """Stand-in for the Treasury send lock (tested in its own file): records
    how many RPC calls had been made on entry and on exit."""
    held = []

    @contextmanager
    def lock():
        entry = {"held": True}
        held.append(entry)
        try:
            yield
        finally:
            entry["held"] = False

    monkeypatch.setattr(evm_service, "treasury_send_lock", lock)
    # Never sleep in a test: a nonce that does not advance gives up at once.
    monkeypatch.setattr(evm_service, "_NONCE_ADVANCE_POLL", 0)
    return held


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


# --- uuid_to_bytes32 -------------------------------------------------------------

# docs/stokvel_integration.md section 1, "Units and IDs".
DOC_UUID = "5f0c2a1e-8d3b-4c6a-9e71-2b4f6d8a0c13"
DOC_BYTES32 = "0x5f0c2a1e8d3b4c6a9e712b4f6d8a0c1300000000000000000000000000000000"


def test_uuid_to_bytes32_matches_the_integration_doc():
    assert Web3.to_hex(uuid_to_bytes32(DOC_UUID)) == DOC_BYTES32


def test_uuid_to_bytes32_gives_the_same_bytes_for_a_uuid_and_its_string():
    value = uuid.UUID(DOC_UUID)

    assert uuid_to_bytes32(value) == uuid_to_bytes32(str(value))


def test_uuid_to_bytes32_is_always_32_bytes():
    for value in (uuid.UUID(int=0), uuid.UUID(int=2**128 - 1), uuid.uuid4()):
        packed = uuid_to_bytes32(value)
        assert len(packed) == 32
        assert packed[16:] == bytes(16)


def test_uuid_to_bytes32_accepts_uppercase():
    assert uuid_to_bytes32(DOC_UUID.upper()) == uuid_to_bytes32(DOC_UUID)


def test_uuid_to_bytes32_accepts_32_hex_digits_without_hyphens():
    assert Web3.to_hex(uuid_to_bytes32(DOC_UUID.replace("-", ""))) == DOC_BYTES32


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-uuid",
        DOC_UUID[:-1],
        DOC_UUID + "0",
        DOC_UUID.replace("5", "g"),
        DOC_UUID + "\n",
        # Forms uuid.UUID accepts but uuidToBytes32 does not.
        "{" + DOC_UUID + "}",
        "urn:uuid:" + DOC_UUID,
    ],
)
def test_uuid_to_bytes32_rejects_strings_that_are_not_uuids(value):
    with pytest.raises(ValueError, match="not a UUID"):
        uuid_to_bytes32(value)


@pytest.mark.parametrize("value", [None, 123, uuid.UUID(DOC_UUID).bytes])
def test_uuid_to_bytes32_rejects_other_types(value):
    with pytest.raises(TypeError):
        uuid_to_bytes32(value)


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


def _sending_web3(nonce=7, on_send=None, **answers):
    """A fake RPC for one send: the nonce advances once the transaction has
    been sent, and the send answers with the real hash of the signed bytes."""
    sent = []

    def send_raw(params):
        if on_send is not None:
            on_send()
        sent.append(params[0])
        return Web3.to_hex(Web3.keccak(hexstr=params[0]))

    def transaction_count(params):
        return hex(nonce + len(sent))

    answers = {
        "eth_getTransactionCount": transaction_count,
        "eth_gasPrice": hex(785_000_000),
        "eth_estimateGas": hex(52_000),
        "eth_sendRawTransaction": send_raw,
        **answers,
    }
    w3, provider = _fake_web3(**answers)
    return w3, provider, sent


def test_submit_transaction_signs_as_the_treasury_and_does_not_wait(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    recipient = Account.create().address
    w3, provider, sent = _sending_web3()

    tx_hash = submit_transaction({"to": recipient, "data": "0x1234"}, w3=w3)

    (raw,) = sent
    assert tx_hash == Web3.to_hex(Web3.keccak(hexstr=raw))
    # Pending nonce before the send, and again after it until it has moved
    # on; no receipt polling.
    nonce_calls = [
        list(params)
        for method, params in provider.calls
        if method == "eth_getTransactionCount"
    ]
    assert nonce_calls == [[treasury.address, "pending"]] * 2
    assert provider.methods()[-2:] == [
        "eth_sendRawTransaction",
        "eth_getTransactionCount",
    ]
    assert "eth_getTransactionReceipt" not in provider.methods()

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


def test_submit_transaction_hands_over_the_hash_before_sending(monkeypatch):
    configure_fake_treasury(monkeypatch)
    seen = []
    w3, provider, sent = _sending_web3()

    def on_signed(tx_hash):
        seen.append((tx_hash, list(provider.methods())))

    tx_hash = submit_transaction(
        {"to": Account.create().address}, w3=w3, on_signed=on_signed
    )

    ((signed_hash, methods_before),) = seen
    assert signed_hash == tx_hash
    assert "eth_sendRawTransaction" not in methods_before
    assert sent  # and it was sent afterwards


def test_submit_transaction_sends_nothing_if_on_signed_raises(monkeypatch):
    configure_fake_treasury(monkeypatch)
    w3, provider, sent = _sending_web3()

    def on_signed(tx_hash):
        raise RuntimeError("could not store the hash")

    with pytest.raises(RuntimeError, match="could not store the hash"):
        submit_transaction({"to": Account.create().address}, w3=w3, on_signed=on_signed)

    assert sent == []
    assert "eth_sendRawTransaction" not in provider.methods()


def test_submit_transaction_holds_the_send_lock_around_every_rpc_call(
    monkeypatch, send_lock
):
    configure_fake_treasury(monkeypatch)
    held_during = []

    def check(params=None):
        held_during.append(bool(send_lock) and send_lock[-1]["held"])

    w3, provider, _ = _sending_web3(on_send=check)
    nonce_answer = provider.answers["eth_getTransactionCount"]

    def nonce(params):
        check()
        return nonce_answer(params)

    provider.answers["eth_getTransactionCount"] = nonce

    submit_transaction({"to": Account.create().address}, w3=w3)

    # The nonce read, the send and the nonce-advanced check: all under one
    # hold of the lock, released afterwards.
    assert held_during == [True, True, True]
    assert len(send_lock) == 1
    assert send_lock[0]["held"] is False


def test_submit_transaction_releases_the_lock_when_the_send_fails(
    monkeypatch, send_lock
):
    configure_fake_treasury(monkeypatch)

    def refuse(params):
        raise ConnectionError("RPC unreachable")

    w3, _, _ = _sending_web3(eth_sendRawTransaction=refuse)

    with pytest.raises(ConnectionError):
        submit_transaction({"to": Account.create().address}, w3=w3)

    assert send_lock[0]["held"] is False


@pytest.mark.parametrize(
    "message",
    [
        "insufficient funds for gas * price + value",
        "nonce too low",
        "replacement transaction underpriced",
    ],
)
def test_a_send_the_rpc_refuses_raises_transaction_rejected(
    monkeypatch, send_lock, message
):
    """An error answer means the node refused the transaction, so it can
    never be mined. The hash was handed over first, the lock is released,
    and the nonce is not waited on."""
    configure_fake_treasury(monkeypatch)
    seen = []
    w3, provider, _ = _sending_web3(eth_sendRawTransaction=RpcError(message))

    with pytest.raises(TransactionRejected, match=re.escape(message)) as rejected:
        submit_transaction(
            {"to": Account.create().address}, w3=w3, on_signed=seen.append
        )

    assert rejected.value.tx_hash == seen[0]
    assert provider.methods()[-1] == "eth_sendRawTransaction"
    assert send_lock[0]["held"] is False


@pytest.mark.parametrize(
    "message", ["upstream request timeout", "internal error", "rate limit exceeded"]
)
def test_an_error_answer_not_known_to_be_a_refusal_is_left_uncertain(
    monkeypatch, send_lock, message
):
    """A gateway can answer its own timeout as a JSON-RPC error after the node
    has taken the transaction. Only a known refusal may be called one, so the
    caller waits on the hash instead of failing a burn that may land."""
    configure_fake_treasury(monkeypatch)
    w3, _, _ = _sending_web3(eth_sendRawTransaction=RpcError(message, code=-32603))

    with pytest.raises(Web3RPCError) as caught:
        submit_transaction({"to": Account.create().address}, w3=w3)

    assert not isinstance(caught.value, TransactionRejected)
    assert send_lock[0]["held"] is False


@pytest.mark.parametrize(
    "message", ["already known", "known transaction: 0xab", "tx already in mempool"]
)
def test_a_send_the_node_already_holds_counts_as_sent(monkeypatch, message):
    configure_fake_treasury(monkeypatch)
    seen = []
    nonce = {"value": 7}

    def already_known(params):
        nonce["value"] = 8  # the node holds it, so the pending nonce moved on
        return RpcError(message)

    w3, _, _ = _sending_web3(
        eth_sendRawTransaction=already_known,
        eth_getTransactionCount=lambda params: hex(nonce["value"]),
    )

    tx_hash = submit_transaction(
        {"to": Account.create().address}, w3=w3, on_signed=seen.append
    )

    assert tx_hash == seen[0]


def test_a_send_that_gets_no_answer_is_not_called_a_refusal(monkeypatch):
    """A dropped connection may still have delivered the transaction, so it
    must not look like a refusal (which would let the caller fail it)."""
    configure_fake_treasury(monkeypatch)

    def drop(params):
        raise ConnectionError("RPC dropped the connection")

    w3, _, _ = _sending_web3(eth_sendRawTransaction=drop)

    with pytest.raises(ConnectionError) as caught:
        submit_transaction({"to": Account.create().address}, w3=w3)

    assert not isinstance(caught.value, TransactionRejected)


def test_transaction_status_is_pending_when_the_rpc_knows_the_hash():
    w3, _ = _fake_web3(
        eth_getTransactionByHash={
            "hash": TX_HASH,
            "blockHash": None,
            "blockNumber": None,
            "from": "0x" + "11" * 20,
            "to": UCTUSD,
            "nonce": "0x7",
            "gas": hex(52_000),
            "gasPrice": hex(785_000_000),
            "input": "0x",
            "value": "0x0",
            "v": "0x1b",
            "r": "0x1",
            "s": "0x1",
            "transactionIndex": None,
            "type": "0x0",
        }
    )

    assert transaction_status(TX_HASH, w3=w3) == evm_service.TX_PENDING


def test_transaction_status_is_unknown_when_the_rpc_has_no_record():
    w3, _ = _fake_web3(eth_getTransactionByHash=None)

    assert transaction_status(TX_HASH, w3=w3) == evm_service.TX_UNKNOWN


def test_submit_transaction_refuses_a_hash_it_did_not_sign(monkeypatch):
    configure_fake_treasury(monkeypatch)
    w3, _, _ = _sending_web3(eth_sendRawTransaction=TX_HASH)

    with pytest.raises(RuntimeError, match="but reported"):
        submit_transaction({"to": Account.create().address}, w3=w3)


def test_submit_transaction_logs_when_the_nonce_does_not_advance(monkeypatch, caplog):
    treasury = configure_fake_treasury(monkeypatch)
    monkeypatch.setattr(evm_service, "_NONCE_ADVANCE_TIMEOUT", 0)
    w3, _, sent = _sending_web3(eth_getTransactionCount=hex(7))

    with caplog.at_level(logging.WARNING, logger="remitx_worker.evm_service"):
        tx_hash = submit_transaction({"to": Account.create().address}, w3=w3)

    # Still reports the hash: the transaction was accepted.
    assert tx_hash == Web3.to_hex(Web3.keccak(hexstr=sent[0]))
    assert "event=evm.nonce_not_advanced" in caplog.text
    for secret in treasury.secrets:
        assert secret not in caplog.text


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


# --- send_transaction -------------------------------------------------------------


def _receipt_web3(wait):
    return SimpleNamespace(eth=SimpleNamespace(wait_for_transaction_receipt=wait))


def _fake_submit(monkeypatch):
    submitted = []

    def submit(tx, w3=None):
        submitted.append((tx, w3))
        return TX_HASH

    monkeypatch.setattr(evm_service, "submit_transaction", submit)
    return submitted


def test_send_transaction_returns_the_hash_and_block(monkeypatch):
    submitted = _fake_submit(monkeypatch)
    waited = []

    def wait(tx_hash, timeout):
        waited.append((tx_hash, timeout))
        return {"transactionHash": tx_hash, "status": 1, "blockNumber": 4242}

    w3 = _receipt_web3(wait)
    tx = {"to": Account.create().address, "data": "0x1234"}

    assert send_transaction(tx, timeout=30, w3=w3) == (TX_HASH, 4242)
    assert submitted == [(tx, w3)]
    assert waited == [(TX_HASH, 30)]


def test_send_transaction_raises_on_a_revert(monkeypatch):
    _fake_submit(monkeypatch)
    w3 = _receipt_web3(
        lambda tx_hash, timeout: {"status": 0, "blockNumber": 4242},
    )

    with pytest.raises(RuntimeError, match="reverted"):
        send_transaction({"to": Account.create().address}, w3=w3)


def test_send_transaction_lets_a_timeout_propagate(monkeypatch):
    _fake_submit(monkeypatch)

    def wait(tx_hash, timeout):
        raise TimeExhausted(f"{tx_hash} not mined in {timeout}s")

    with pytest.raises(TimeExhausted):
        send_transaction(
            {"to": Account.create().address}, timeout=1, w3=_receipt_web3(wait)
        )


# --- burn ------------------------------------------------------------------------


def test_the_abi_has_burn_and_total_supply():
    token = Web3().eth.contract(address=Web3.to_checksum_address(UCTUSD), abi=ERC20_ABI)

    # Selectors as found in the deployed UCTUSD bytecode.
    assert token.encode_abi("burn", args=[1]).startswith("0x42966c68")
    assert token.encode_abi("totalSupply") == "0x18160ddd"


def test_burn_tokens_burns_exactly_the_amount_from_the_treasury(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    seen = []
    w3, provider, sent = _sending_web3()

    tx_hash = burn_tokens(Decimal("5.12345678"), on_signed=seen.append, w3=w3)

    (raw,) = sent
    assert seen == [tx_hash]
    assert Account.recover_transaction(raw) == treasury.address
    fields = _decode_legacy(raw)
    assert fields["to"].lower() == UCTUSD
    # burn(uint256), then exactly 5.12345678 at 18 decimals: nothing rounded,
    # and nothing to do with what the Treasury holds.
    assert fields["data"] == bytes.fromhex("42966c68") + encode(
        ["uint256"], [5_123_456_780_000_000_000]
    )
    assert "eth_getTransactionReceipt" not in provider.methods()


@pytest.mark.parametrize(
    ("amount", "error"),
    [
        (Decimal("0"), ValueError),
        (Decimal("-1"), ValueError),
        (Decimal("0.0000000000000000001"), ValueError),  # finer than a base unit
        (Decimal("NaN"), ValueError),
        (1.5, TypeError),
        (1, TypeError),
    ],
)
def test_burn_tokens_rejects_bad_amounts_before_any_rpc_call(
    monkeypatch, amount, error
):
    configure_fake_treasury(monkeypatch)
    w3, provider, _ = _sending_web3()

    with pytest.raises(error):
        burn_tokens(amount, w3=w3)

    assert provider.calls == []


def test_wait_for_receipt_lets_a_timeout_propagate():
    def wait(tx_hash, timeout):
        raise TimeExhausted(f"{tx_hash} not mined in {timeout}s")

    with pytest.raises(TimeExhausted):
        wait_for_receipt(TX_HASH, timeout=1, w3=_receipt_web3(wait))
