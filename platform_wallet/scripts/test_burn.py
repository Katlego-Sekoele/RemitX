"""
Confirm the UCTUSD burn method with one tiny real burn from the Treasury (#278).

Calls the token's `burn(uint256)` from the RemitX Treasury Wallet on XRPL EVM
Testnet, then shows that `totalSupply` fell by exactly the amount burned. The
result goes on #278 and in docs/stokvel_integration.md section 8.

Without --send this is a dry run: every check below runs and the burn is
simulated with `eth_call`, but nothing is signed or sent. A real burn needs
--send, and Sian's written OK first.

Refuses to run unless:
- the RPC is chain 1449000 (XRPL EVM Testnet);
- the token is UCTUSD at 0x7055071C7B79A859d9514e62833BFf041ce71074;
- the decrypted key derives the Treasury, 0x6C350A0A9031DE51dF0535e2e88872Cd7330F2e7,
  and EVM_TREASURY_ADDRESS says the same;
- the amount is at most 10^12 base units (0.000001 UCTUSD). The default is 1.

It sends nothing but `burn` and never prints the key, its ciphertext, the
account or the transaction. The hash is printed before the send. Run a real
burn only while no worker is sending from the Treasury (before #278 is
deployed, or with the worker stopped): this script does not take the
worker's Treasury send lock, so the two could pick the same nonce.

EVM_TREASURY_KEY_ENCRYPTED, EVM_ENCRYPTION_KEY and EVM_TREASURY_ADDRESS come
from the environment or the repo-root .env, as for check_balances.py.

To Run:
    pip install -r platform_wallet/scripts/requirements.txt
    python platform_wallet/scripts/test_burn.py                        # dry run
    python platform_wallet/scripts/test_burn.py --send --base-units 1  # REAL burn
"""

import argparse
import os
import sys
from decimal import Decimal

from cryptography.fernet import InvalidToken
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError

# Same connection, settings and decryption as the wallet script.
from create_evm_platform_wallet import (
    _ENV_PATH,
    DEFAULT_EXPLORER_URL,
    DEFAULT_UCTUSD_CONTRACT,
    _decrypt_secret,
    _setting,
    connect,
)

# Hard-coded on purpose: a misconfigured .env must not point a real burn at
# another chain, token or wallet.
EXPECTED_CHAIN_ID = 1449000
EXPECTED_UCTUSD_CONTRACT = "0x7055071C7B79A859d9514e62833BFf041ce71074"
EXPECTED_TREASURY = "0x6C350A0A9031DE51dF0535e2e88872Cd7330F2e7"
MAX_BASE_UNITS = 10**12  # 0.000001 UCTUSD at 18 decimals
RECEIPT_TIMEOUT_SECONDS = 120

TOKEN_ABI = [
    {
        "name": "burn",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "value", "type": "uint256"}],
        "outputs": [],
    },
    {
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]


def _base_units(value: str) -> int:
    """argparse type: a whole number of base units, 1 to MAX_BASE_UNITS."""
    try:
        units = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {value}") from None
    if not 1 <= units <= MAX_BASE_UNITS:
        raise argparse.ArgumentTypeError(
            f"must be between 1 and {MAX_BASE_UNITS} base units, got {units}"
        )
    return units


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument(
        "--base-units",
        type=_base_units,
        default=1,
        help=f"how much to burn, in base units (default 1, at most {MAX_BASE_UNITS})",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="really sign and send the burn (default: dry run, nothing sent)",
    )
    return parser.parse_args()


def _same_address(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def _load_treasury():
    """The Treasury's account from its encrypted key. Never echoes either."""
    encrypted = os.environ.get("EVM_TREASURY_KEY_ENCRYPTED", "")
    encryption_key = os.environ.get("EVM_ENCRYPTION_KEY", "")
    if not (encrypted and encryption_key):
        raise SystemExit("EVM_TREASURY_KEY_ENCRYPTED / EVM_ENCRYPTION_KEY not set.")
    try:
        private_key = _decrypt_secret(encrypted, encryption_key)
    except (InvalidToken, ValueError):
        raise SystemExit(
            "EVM_TREASURY_KEY_ENCRYPTED does not decrypt with EVM_ENCRYPTION_KEY."
        ) from None
    try:
        account = Account.from_key(private_key)
    except Exception:
        raise SystemExit("The decrypted key is not a valid EVM private key.") from None
    if not _same_address(account.address, EXPECTED_TREASURY):
        raise SystemExit(
            f"The key derives {account.address}, not the Treasury {EXPECTED_TREASURY}."
        )
    return account


def _check_settings() -> None:
    token = _setting("UCTUSD_CONTRACT_ADDRESS", DEFAULT_UCTUSD_CONTRACT)
    if not _same_address(token, EXPECTED_UCTUSD_CONTRACT):
        raise SystemExit(
            f"UCTUSD_CONTRACT_ADDRESS is {token}, not {EXPECTED_UCTUSD_CONTRACT}."
        )
    treasury = os.environ.get("EVM_TREASURY_ADDRESS", "")
    if not _same_address(treasury, EXPECTED_TREASURY):
        raise SystemExit(
            f"EVM_TREASURY_ADDRESS is {treasury or '(unset)'}, not {EXPECTED_TREASURY}."
        )


def _show(label: str, raw: int, decimals: int) -> None:
    print(f"  {label:<24}: {raw} base units ({Decimal(raw).scaleb(-decimals)} UCTUSD)")


def _supply_and_balance(token, treasury: str, block="latest") -> tuple[int, int]:
    return (
        token.functions.totalSupply().call(block_identifier=block),
        token.functions.balanceOf(treasury).call(block_identifier=block),
    )


def main() -> None:
    args = _parse_args()
    load_dotenv(_ENV_PATH)
    amount = args.base_units

    _check_settings()
    w3 = connect()
    if w3.eth.chain_id != EXPECTED_CHAIN_ID:
        raise SystemExit(f"RPC is chain {w3.eth.chain_id}, not {EXPECTED_CHAIN_ID}.")
    account = _load_treasury()
    treasury = Web3.to_checksum_address(EXPECTED_TREASURY)

    token_address = Web3.to_checksum_address(EXPECTED_UCTUSD_CONTRACT)
    if not w3.eth.get_code(token_address):
        raise SystemExit(f"No contract deployed at {token_address} on this chain.")
    token = w3.eth.contract(address=token_address, abi=TOKEN_ABI)
    decimals = token.functions.decimals().call()

    supply_before, balance_before = _supply_and_balance(token, treasury)
    print(f"Chain     : {EXPECTED_CHAIN_ID}")
    print(f"Token     : {token_address} (UCTUSD, {decimals} decimals)")
    print(f"Treasury  : {treasury} (key decrypted and checked; never printed)")
    _show("burn amount", amount, decimals)
    _show("totalSupply before", supply_before, decimals)
    _show("Treasury balance before", balance_before, decimals)
    if balance_before < amount:
        raise SystemExit("The Treasury holds less than the burn amount.")

    burn = token.functions.burn(amount)
    try:
        burn.call({"from": treasury})
        gas = burn.estimate_gas({"from": treasury})
    except ContractLogicError as exc:
        raise SystemExit(f"Simulated burn reverted: {exc}") from None
    print(f"Simulated : burn({amount}) from the Treasury succeeds; gas estimate {gas}")

    if not args.send:
        print("\nDry run: nothing was signed or sent.")
        print("After Sian's written OK, re-run with --send to burn for real.")
        return

    tx = burn.build_transaction(
        {
            "from": treasury,
            "nonce": w3.eth.get_transaction_count(treasury, "pending"),
            "chainId": EXPECTED_CHAIN_ID,
            "gasPrice": w3.eth.gas_price,
            "gas": gas,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = Web3.to_hex(signed.hash)
    explorer = _setting("EVM_EXPLORER_URL", DEFAULT_EXPLORER_URL)
    print(f"\nSigned    : {tx_hash}")
    print(f"Explorer  : {explorer}/tx/{tx_hash}")

    sent = Web3.to_hex(w3.eth.send_raw_transaction(signed.raw_transaction))
    if sent.lower() != tx_hash.lower():
        raise SystemExit(f"The RPC accepted the burn but reported hash {sent}.")
    print(f"Sent; waiting up to {RECEIPT_TIMEOUT_SECONDS}s for the receipt...")
    receipt = w3.eth.wait_for_transaction_receipt(
        tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS
    )
    block = receipt["blockNumber"]
    if receipt["status"] != 1:
        print(f"FAIL  the burn reverted in block {block}.")
        sys.exit(1)
    print(f"Mined     : block {block}, status 1")

    # Read either side of the burn's own block, so another transfer landing
    # meanwhile cannot blur the result; fall back to the reads taken before
    # the send if the node no longer has that block's state.
    try:
        supply_before, balance_before = _supply_and_balance(token, treasury, block - 1)
        supply_after, balance_after = _supply_and_balance(token, treasury, block)
    except Exception:
        supply_after, balance_after = _supply_and_balance(token, treasury)
    _show("totalSupply before", supply_before, decimals)
    _show("totalSupply after", supply_after, decimals)
    _show("Treasury balance after", balance_after, decimals)

    supply_fell = supply_before - supply_after
    balance_fell = balance_before - balance_after
    ok = supply_fell == amount and balance_fell == amount
    print(
        f"{'PASS' if ok else 'FAIL'}  totalSupply fell by {supply_fell}, the "
        f"Treasury balance by {balance_fell} (expected {amount} each)"
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
