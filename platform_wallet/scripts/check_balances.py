"""
Check the RemitX treasury wallet's balances on XRPL EVM Testnet.

Prints the treasury's native (XRP) and UCTUSD balances, and optionally a
deployer's XRP. With --min-uctusd / --min-xrp it reports pass or fail against
each threshold and exits non-zero if either is short, so it can gate a script.

Read-only: it needs no private key and never builds or signs a transaction.
EVM_RPC_URL, UCTUSD_CONTRACT_ADDRESS and EVM_TREASURY_ADDRESS come from the
environment or the repo-root .env, with the same defaults as
create_evm_platform_wallet.py.

To Run:
    pip install -r platform_wallet/scripts/requirements.txt
    python platform_wallet/scripts/check_balances.py \
        [--deployer 0x...] [--min-uctusd 100] [--min-xrp 1]
"""

import argparse
import os
import sys
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from web3 import Web3

# Same connection, token checks and defaults as the wallet script.
from create_evm_platform_wallet import _ENV_PATH, connect, read_balances


def _address(value: str) -> str:
    """argparse type: a checksummed EVM address."""
    if not Web3.is_address(value):
        raise argparse.ArgumentTypeError(f"not a valid EVM address: {value}")
    return Web3.to_checksum_address(value)


def _amount(value: str) -> Decimal:
    """argparse type: a non-negative decimal amount."""
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"not a number: {value}") from None
    if not amount.is_finite() or amount < 0:
        raise argparse.ArgumentTypeError(f"must be a non-negative number: {value}")
    return amount


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument(
        "--deployer", type=_address, help="also print this address's XRP balance"
    )
    parser.add_argument(
        "--min-uctusd", type=_amount, help="fail if the treasury holds less UCTUSD"
    )
    parser.add_argument(
        "--min-xrp", type=_amount, help="fail if the treasury holds less XRP"
    )
    return parser.parse_args()


def _check(label: str, balance: Decimal, minimum: Decimal | None) -> bool:
    """Print pass/fail for one threshold; True when it passes or is unset."""
    if minimum is None:
        return True
    ok = balance >= minimum
    print(f"  {'PASS' if ok else 'FAIL'}  {label} {balance} (min {minimum})")
    return ok


def main() -> None:
    args = _parse_args()
    load_dotenv(_ENV_PATH)

    treasury = os.environ.get("EVM_TREASURY_ADDRESS")
    if not treasury or not Web3.is_address(treasury):
        raise SystemExit("EVM_TREASURY_ADDRESS is not set to a valid address.")
    treasury = Web3.to_checksum_address(treasury)

    w3 = connect()
    native, uctusd = (Decimal(b) for b in read_balances(w3, treasury))

    print(f"Treasury  {treasury}")
    print(f"  XRP     : {native}")
    print(f"  UCTUSD  : {uctusd}")
    if args.deployer:
        deployer_xrp = w3.from_wei(w3.eth.get_balance(args.deployer), "ether")
        print(f"Deployer  {args.deployer}")
        print(f"  XRP     : {deployer_xrp}")

    if args.min_uctusd is None and args.min_xrp is None:
        return
    print("Checks")
    # Evaluate both so each prints, then fail if either is short.
    results = [
        _check("treasury UCTUSD", uctusd, args.min_uctusd),
        _check("treasury XRP", native, args.min_xrp),
    ]
    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
