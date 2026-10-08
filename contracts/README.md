# RemitX stokvel contract

`StokvelVault` holds the money for every RemitX stokvel on the XRPL EVM
Testnet. One deployment serves all stokvels
([ADR 0002](../docs/adr/0002-one-contract-many-stokvels.md)). The backend
talks to it through the Treasury Wallet; members never hold keys.

The full interface (functions, errors, events, views) is the shared contract
in [docs/stokvel_integration.md §1](../docs/stokvel_integration.md). Code
against that, not against this README. The per-ticket history of changes is
in [smart_contracts_changes.md](smart_contracts_changes.md).

## Trust assumption

**The contract trusts the backend to identify the contributing member**
(brief §7.4). Members have no keys, so every call comes from the Treasury
Wallet, and the contract cannot tell who really paid. It only checks that the
named member belongs to the current cycle and has not paid that round yet.
The backend's ledger is the evidence of who paid. A compromised operator key
could misattribute contributions (but not release a pool early: the release
rules below are enforced on-chain regardless of who calls).

## How it works

```
createStokvel(id, contribution)
startCycle(id, members, roundStartTimes, roundDeadlines, payoutTimes)
contribute(id, round, memberId)     x members x rounds
finalise(id, round)                 for rounds that become due with time
```

- **A stokvel** is registered once with a fixed UCTUSD contribution.
- **A cycle** fixes the members (array order is the payout order: round *i*
  pays `members[i]`) and a schedule with one round per member. When a cycle
  closes, the next one can start with new members and a new schedule.
- **Rounds fill in order.** A round accepts contributions only once every
  earlier round is fully paid. Late contributions are accepted; the deadline
  is informational.
- **Release rule (doc D5, D12).** Round N's pool is released to the Treasury
  Wallet when round N is fully paid, round N+1 is fully paid (or N is the last
  round), **and** `payoutTimes[N]` has passed. If a contribution completes the
  condition after the payout time, the same transaction releases the round.
  Otherwise the backend's scheduled task calls `finalise` once the time
  passes. The cycle closes after its last round is released.
- **A blocked round stays blocked** until the last member pays. There are no
  penalties on-chain.

### Roles

| Role | Held by | Can |
|---|---|---|
| `DEFAULT_ADMIN_ROLE` | Deployer (platform owner) | Grant roles, `pause`, `unpause` |
| `OPERATOR_ROLE` | Treasury Wallet (backend) | `createStokvel`, `startCycle`, `contribute`, `finalise` |

The two must be different addresses (the constructor enforces it), so the key
that moves tokens cannot also control the emergency stop. Pausing stops
`contribute` and `finalise` for every stokvel and never changes the release
conditions.

### IDs and privacy

Stokvel and member IDs are database UUIDs packed left-aligned into `bytes32`
(the 16 UUID bytes, then 16 zero bytes). `uuidToBytes32` in
[test/helpers.ts](test/helpers.ts) is the reference; the backend must produce
the same bytes. Use per-stokvel member row IDs (`stokvel_members.id`), not
user IDs: everything on-chain is public and permanent, and a user ID would
link one person's stokvels. No names, accounts or other personal data go
on-chain.

## Using it from the backend

- **ABI:** [abi/StokvelVault.json](abi/StokvelVault.json). Load this file;
  do not copy the ABI by hand. It is regenerated with `npm run export:abi`,
  and a test fails if it drifts from the contract.
- **Address:** `STOKVEL_CONTRACT_ADDRESS` in the root `.env`, also recorded in
  [deployments/](deployments/) and doc §2 after each deployment.
- **Amounts** are UCTUSD smallest units (18 decimals).
- **Allowance** (agreed with the backend; doc §1 "Treasury allowance"):
  `contribute` pulls from the Treasury with `safeTransferFrom`, so the
  Treasury must approve the contract first.
  - Approve once per contract address at setup:
    `UCTUSD.approve(STOKVEL_CONTRACT_ADDRESS, type(uint256).max)`.
  - Before each `contribute`, check `allowance(treasury, contract)` and
    re-approve if it is below the contribution. This also covers a redeploy
    to a new address.
  - This is safe because the contract only pulls from `msg.sender`, and only
    the operator (the Treasury itself) can call `contribute`.
  - A missing allowance reverts with the token's
    `ERC20InsufficientAllowance`, which is a backend fault.
- **Errors** map to API responses in doc §6.

## Develop

```bash
cd contracts
npm ci
npx hardhat test          # 69 tests
npx hardhat coverage      # line and branch coverage
npm run export:abi        # after any interface change; commit abi/
```

Hardhat 2, Solidity 0.8.24 (`evmVersion: paris`), OpenZeppelin Contracts v5.
TypeScript is pinned to 5.8 because TypeScript 7 breaks `ts-node`.

| Path | What |
|---|---|
| `src/StokvelVault.sol` | The contract |
| `src/mocks/` | Test-only tokens (never deployed) |
| `test/` | Tests: setup, contribute, pause, views, ABI drift, and shared `helpers.ts` |
| `scripts/deploy.ts` | Deploy script |
| `scripts/export-abi.js` | ABI export |
| `abi/` | Exported ABI for the backend (committed) |
| `deployments/` | One JSON record per network: address, block, arguments (committed) |

## Deploy

Settings come from the repo-root `.env`:

| Name | Meaning |
|---|---|
| `DEPLOYER_PRIVATE_KEY` | Deployer key; becomes the admin. **Local `.env` only, never committed** |
| `EVM_TREASURY_ADDRESS` | Treasury Wallet: operator and release target |
| `UCTUSD_CONTRACT_ADDRESS` | Optional; defaults to the brief's UCTUSD address |
| `MAX_STOKVEL_MEMBERS` | Optional; defaults to 3 |

```bash
npm run deploy:local      # dry run on a local chain; writes nothing
npm run deploy:testnet    # XRPL EVM Testnet (chain 1449000)
```

The script checks the settings, the token and the deployer's gas before
sending anything, and refuses to overwrite an existing deployment record
unless `FORCE_REDEPLOY=1`. After deploying it checks the roles and settings,
writes `deployments/xrplEvmTestnet.json`, and prints the verify command and
the `STOKVEL_CONTRACT_ADDRESS` line.
