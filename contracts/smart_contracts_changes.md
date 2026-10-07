# Smart contract changes

A log of every change to the stokvel smart contracts, one entry per ticket
(milestone: *Smart Contract Creation and Connection*). Newest first.

Each entry records: the ticket, what changed, the files touched, decisions
taken (and why), and anything left open for a later ticket.

---

## #197 Stokvel contract: stokvels and cycles

**Date:** 2026-10-06
**Status:** Implemented, tests passing (20), not yet deployed

### What changed

- New `contracts/` Hardhat project (Hardhat 2, Solidity 0.8.24,
  OpenZeppelin Contracts v5, TypeScript tests).
- New contract `StokvelVault`: one deployment holds every stokvel, keyed by
  a `bytes32` stokvel ID.
  - **Roles** (`AccessControl`): `DEFAULT_ADMIN_ROLE` (Administrator) and
    `OPERATOR_ROLE` (Treasury Wallet).
  - **Fixed at deployment** (immutable): UCTUSD `token` and `releaseTarget`.
    Member limits are constants: `MIN_MEMBERS = 2`, `MAX_MEMBERS = 12`.
  - **Storage** as in the ticket's sketch: `Stokvel` struct (members in
    payout order, contribution, startTime, interval, currentRound, closed)
    plus `isMember`, `paid`, `paidCount` and `roundPool` mappings. The last
    three are declared now and used from #198.
  - `createStokvel(id, members, contribution, startTime, interval)`, operator only.
    Emits `StokvelCreated`.
  - `updateStokvel(...)`, operator only and only before `startTime`. Replaces
    terms and members and emits `StokvelUpdated`.
  - Views: `getStokvel(id)`, `exists(id)`, `hasStarted(id)`, plus the
    public mapping getters.
  - Inherits `Pausable` and `ReentrancyGuard` and wires in `SafeERC20`, ready
    for #198 and #199.
- Custom errors for every rejection: `ZeroAddress`, `ZeroStokvelId`,
  `StokvelExists`, `StokvelNotFound`, `InvalidMemberCount`, `ZeroMemberId`,
  `DuplicateMember`, `ZeroContribution`, `ZeroInterval`, `StartTimeInPast`,
  `CycleStarted`.

### Files

- `contracts/package.json`, `package-lock.json`, `hardhat.config.ts`,
  `tsconfig.json`, `.gitignore`
- `contracts/src/StokvelVault.sol`
- `contracts/test/StokvelVault.create.test.ts`
- `contracts/smart_contracts_changes.md` (this file)

### Acceptance criteria

- [x] Duplicate ID, duplicate member, fewer than 2 or more than 12 members,
  zero contribution or zero interval all revert.
- [x] Only the operator can create.
- [x] Settings are fixed once the cycle starts (`updateStokvel` reverts with
  `CycleStarted` from `startTime` onwards).

### Decisions

- **"Cycle starts" means `block.timestamp >= startTime`.** The contract needs
  no separate start call, and the terms lock on their own. `startTime` must
  not be in the past when it is set.
- **Changes before the start go through `updateStokvel`.** Terms are replaced
  whole, so the Organiser can still change payout order or members until
  round 0 opens.
- **The zero ID and zero member ID are rejected.** A zero value usually means
  a hashing bug in the backend, and a stokvel's existence is checked by its
  member count, so an empty ID would be ambiguous.
- **`releaseTarget` is a constructor argument.** This works with either
  option in #207 (one Treasury Wallet or a separate settlement wallet).
- **`evmVersion: paris`.** It avoids newer opcodes (PUSH0, MCOPY) that the
  XRPL EVM Testnet may not support. Confirm this before deploying in #200.
- **TypeScript is pinned to 5.8.** TypeScript 7 breaks `ts-node`, which
  Hardhat 2 uses to load TypeScript tests.
- **Member IDs must be HMAC-derived (added 2026-10-07).** The contract only
  stores opaque IDs and counters. But a plain hash such as
  `keccak256("user-sipho")`, as in the ticket's example, can be reversed by
  guessing inputs. Reusing one ID across stokvels would also link a person's
  groups. The rule is `HMAC(serverSecret, stokvelId || userId)`. It is
  documented in the NatSpec on `createStokvel`, and the tests now derive IDs
  this way. The contract cannot enforce it, so the backend must (#201).

### Edge-case tests (added 2026-10-07)

16 tests added in an "edge cases" block, bringing the total to 36, all
passing. No contract changes were needed.

- **Time boundaries:** `startTime` equal to the block time is accepted and
  has started at once. An update 1 s before the start succeeds, and one at
  exactly the start reverts. An update that moves the start into the past
  reverts. Postponing the start keeps the terms editable past the old start.
- **Member lists:** exactly 2 members is accepted. A duplicate as the 12th
  member reverts.
- **Atomicity:** a failed create leaves no state behind (the ID is still
  free). A failed update leaves the old terms and members unchanged.
- **Updates:** a reorder-only update works. A member removed in one update
  can be added back in the next. Shrinking from 12 members to 2 clears
  `isMember` for all 10 removed members. Updating one stokvel leaves others
  untouched.
- **Values:** a contribution of 1 and an interval of 1 are accepted.
- **Roles:** the admin can move the operator role to a new Treasury Wallet,
  after which the old one is locked out. The operator cannot grant roles.

### Left open / for later tickets

- **Overflow limits for #198:** create accepts any non-zero `contribution`
  and `interval` and any future `startTime`. With extreme values,
  `contribution × members` or `startTime + interval × rounds` would overflow
  and revert in #198's arithmetic, so the stokvel could never complete.
  Solidity 0.8 reverts on overflow, so funds are safe, and only the operator
  can create. Consider sensible upper bounds when #198 adds the arithmetic.

- **Pausing:** `pause()` and `unpause()` (admin only) and `whenNotPaused`
  guards are #199. Create and update are not pause-gated yet. Decide in #199
  whether they should be.
- **Starting a new cycle after `closed`** (members continue or leave, and the
  Organiser resets the payout order) is not on-chain yet. It needs the
  close logic from #198 first.
- **Cancellation and refunds:** waiting on decision #208.
- **Release target:** waiting on decision #207. The address is passed at
  deployment either way.
- **`CONTEXT.md`** (glossary referenced by the ticket) does not exist in the
  repo yet.
- **#201 (backend connection):** derive member IDs as
  `HMAC(serverSecret, stokvelId || userId)`, with the secret held outside the
  database, like the XRPL key encryption key. Store the mapping from member
  ID to user in the database. Remember that every ID sent on-chain is public
  and permanent, including IDs removed later by `updateStokvel` (they stay
  in the `StokvelCreated` event).
- **Citation unverified:** the ticket cites "brief section 7.4" for keeping
  personal data off-chain. Neither brief in the repo has that section or
  mentions stokvels, and the contract comment still repeats it. Confirm the
  source with the ticket author.

### How to run

```bash
cd contracts
npm ci
npx hardhat test
```
