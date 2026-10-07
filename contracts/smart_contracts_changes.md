# Smart contract changes

A log of every change to the stokvel smart contracts, one entry per ticket
(milestone: *Smart Contract Creation and Connection*). Newest first.

Each entry records: the ticket, what changed, the files touched, decisions
taken (and why), and anything left open for a later ticket.

---

## #199 Stokvel contract: pause and resume

**Date:** 2026-10-07
**Branch:** `feature/199-pause-resume` (stacked on
`feature/198-stokvel-contributions`)
**Status:** Contract part done, tests passing (69 in total, 12 new).
Backend and frontend parts not started (see "Left open").

### What changed

- `pause()` and `unpause()`, admin role only (OpenZeppelin `Pausable`).
  OpenZeppelin's `Paused(account)` and `Unpaused(account)` events record who
  did it. The public `paused()` view lets the backend show the state.
- `contribute` already had `whenNotPaused` (#198). Finalisation only runs
  inside `contribute`, so pausing stops every token movement: contributions,
  finalisation and pool release.
- **New constructor check `AdminIsOperator`:** deployment reverts if the
  admin and the operator are the same address.

### Files

- `contracts/src/StokvelVault.sol`
- `contracts/test/StokvelVault.pause.test.ts`
- `contracts/smart_contracts_changes.md`

### Acceptance criteria

- [x] The operator and ordinary accounts cannot pause or resume. The admin
  can, and the events record the admin's address.
- [x] While paused, every token-moving call reverts with `EnforcedPause`.
  This includes a contribution that would trigger finalisation, and a
  contribution to a different stokvel. Token balances and all round state
  are identical before and after.
- [x] After resuming, payout conditions are unchanged. A round one short is
  still one short, nothing finalises on resume (even after deadlines pass
  during the pause), and the duplicate and round-order rules still apply.
  The ticket's example runs as written, and a full cycle completes across
  repeated pause and resume.
- [ ] Backend shows the paused state and refuses to submit while paused.
  **Not done.** It needs the backend chain client from #201 and #205.

### Decisions

- **Create and update are not paused.** The ticket defines pause as
  halting contributions, finalisation and refunds, which are the
  token-moving calls. Create and update move no tokens, and gating them
  would give the Administrator a say over a group's terms, which the ticket
  rules out. This closes the open question from #197.
- **Views keep working while paused**, so the backend and admin screen can
  still show every stokvel's state.
- **The admin and operator must be different keys at deployment.** This
  enforces the ticket's rule that the key that moves tokens must not also
  control the emergency stop. Limitation: the admin can still grant itself
  `OPERATOR_ROLE` later through `AccessControl`. That is inherent to
  role management, and the audit log (and on-chain `RoleGranted` events)
  is the control.
- **Pause is checked first.** A paused contract reverts with
  `EnforcedPause` even for otherwise invalid input, so callers get one
  clear reason.
- **Refunds:** not built yet (#208). Any refund function added later must
  carry `whenNotPaused`.

### Left open / for later tickets

- **Backend (this ticket, blocked):** an admin route and controller that
  call `pause()` and `unpause()`, write to the audit log, expose
  `paused()`, and refuse stokvel submissions while paused. The API has no
  EVM client yet: web3.py, the RPC URL and the contract address arrive with
  #201 and #204, and key storage with #205. Pausing also needs the
  **admin** key on the server, separate from the Treasury Wallet key, which
  #205 does not cover yet.
- **Frontend (this ticket, blocked):** the pause and resume control on the
  admin screen depends on the backend route above.
- **Deployment (#200):** pass different addresses for `admin` and
  `operator`.

---

## #198 Stokvel contract: contributions and finalisation

**Date:** 2026-10-07
**Branch:** `feature/198-stokvel-contributions` (stacked on
`feature/197-stokvel-contract`)
**Status:** Implemented, tests passing (57 in total, 21 new), not yet deployed

### What changed

- `contribute(id, round, memberId, amount)`: operator only,
  `whenNotPaused`, `nonReentrant`. Checks, in order: the stokvel exists,
  is not closed, and its cycle has started; the round is the open round; the
  member belongs to this stokvel; the member has not paid this round; the
  amount equals the contribution. It then marks the member paid, adds to
  `roundPool`, emits `ContributionMade`, pulls the tokens from the Treasury
  Wallet (`safeTransferFrom`) and finalises any round that is ready.
- Internal `_finaliseReady`: round N finalises when it is full and round
  N+1 is also full, or at once if N is the last round. For each round it
  zeroes the pool, advances `currentRound` (and sets `closed` after the last
  round), emits `RoundFinalised` (and `StokvelClosed`), then transfers the
  pool to `releaseTarget`. It loops, so the final contribution of a cycle
  releases the last two rounds together.
- New views: `openRound(id)`, `payoutTime(id, round)` and
  `nextRecipient(id)`. "Has a member paid" uses the existing public `paid`
  getter.
- Events: `ContributionMade(id, round, memberId, amount)`,
  `RoundFinalised(id, round, recipientId, pool)` and `StokvelClosed(id)`.
  `id` is indexed in all three, and `round` and `memberId` where present.
- New errors: `CycleNotStarted`, `StokvelIsClosed`, `NotMember`,
  `AlreadyPaid`, `WrongAmount`, `RoundNotOpen`, `RoundOutOfRange`.
- Test-only mocks, never deployed: `src/mocks/MockUCTUSD.sol` and
  `src/mocks/ReentrantToken.sol`. The second calls back into the vault
  during a transfer.

### Files

- `contracts/src/StokvelVault.sol`
- `contracts/src/mocks/MockUCTUSD.sol`, `contracts/src/mocks/ReentrantToken.sol`
- `contracts/test/StokvelVault.contribute.test.ts`
- `contracts/smart_contracts_changes.md`

### Acceptance criteria

- [x] Tests for each revert: wrong amount (too low, too high, zero),
  duplicate, unknown member (including a member of another stokvel),
  unauthorised sender, plus the ticket's example sequence step by step.
- [x] A round blocked because one member has not paid never finalises,
  even after every deadline passes.
- [x] No double finalisation. Each round is finalised exactly once over a
  full cycle, a finalised round rejects further contributions, and a
  reentrant token is blocked both during the pool release and during the
  contribution pull, with the whole transaction rolled back.
- [x] The cycle closes after the last round. This is tested on 3-, 2- and
  12-member stokvels; the 12-member run does 144 contributions, and the
  vault balance equals the unreleased pools after every round.

### Decisions

- **Open question answered as recommended: rounds fill in order.** Round
  N+1 accepts contributions only once round N is full, so exactly one round
  is open at a time (`openRound`). This removes the ambiguity in "finalise N
  once N+1 is full".
- **`contribute` takes an explicit `amount`.** The ticket's signature has
  none, but "wrong amount reverts" needs one to test against. It also makes
  a backend bug (such as wrong decimals) revert instead of silently pulling
  the stored amount. **#201 must pass the amount.**
- **No contributions before `startTime`.** Terms can change until the start
  (#197). Accepting money first would let `updateStokvel` drop a member who
  had already paid.
- **Paying ahead is allowed, and lateness is not penalised.** Rounds are not
  time-gated beyond the start: round N+1 opens as soon as round N is full,
  whatever the clock says. This follows the ticket's example, which pays
  round 1 within seconds. `payoutTime` is informational: it returns the
  scheduled end of a round, start + (round + 1) × interval.
- **Recipient = `members[round]`.** The entitled member is recorded in
  `RoundFinalised`, not in extra storage, because the payout order already
  fixes it.
- **Trust assumption:** members hold no keys, so the contract trusts the
  operator to name the right member. This is documented in NatSpec on
  `contribute`, and the backend ledger is the evidence.
- **Overflow:** `payoutTime` computes in `uint256`, and a test with the
  `uint64` maximum confirms it cannot overflow. This partly closes the #197
  overflow note. The pool sum still uses checked arithmetic, so an absurd
  contribution would revert rather than miscount.

### Left open / for later tickets

- **Pausing (#199):** `contribute` already carries `whenNotPaused`, but
  `pause()` and `unpause()` do not exist yet, so the pause behaviour is
  untested.
- **Sending limits (#201):** the ticket says contributions count toward a
  member's own sending limits. That is enforced in the backend, not the
  contract.
- **Release target (#207)** and **cancellation and refunds (#208)** are
  still undecided. A stuck round currently stays stuck, which matches the
  brief's "no recovery" position.
- **A closed stokvel cannot start a new cycle.** Closing works: the final
  contribution releases the last round, sets `closed`, and emits
  `StokvelClosed`, after which every contribution and the
  `openRound`/`nextRecipient` views revert. But #197's rule "between cycles,
  members continue or leave; the Organiser resets the payout order" has no
  on-chain function yet. It would need something like
  `startNextCycle(id, members, startTime)`, which would clear `paid`,
  `paidCount` and `isMember` and reset `currentRound` and `closed`. Until
  then, a new cycle means creating a new stokvel with a new ID. Raise this
  with the team: is it in scope, and which ticket owns it?
- **Deployment and gas on the XRPL EVM (#200):** the worst case is the final
  contribution of a 12-member cycle, which makes two releases. It stays
  under 300k gas locally.

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
