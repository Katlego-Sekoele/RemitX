# Smart contract changes

A log of every change to the stokvel smart contracts, one entry per ticket
(milestone: *Smart Contract Creation and Connection*). Newest first.

Each entry records: the ticket, what changed, the files touched, decisions
taken (and why), and anything left open for a later ticket.

---

## #218 R1-04 Deploy to the XRPL EVM Testnet

**Date:** 2026-10-08
**Branch:** `feature/218-deploy-testnet` (stacked on
`feature/212-contract-interface-d12`)
**Status:** Script ready and tested locally. **Not deployed:** the
deployer has 0 test XRP (waiting on #224).

### What changed

- **`hardhat.config.ts`:** loads the repo-root `.env` (with `dotenv`) and
  adds the `xrplEvmTestnet` network (RPC `https://rpc.testnet.xrplevm.org`,
  chain 1449000) and Blockscout explorer settings for `hardhat verify`. The
  deployer key is read only from `DEPLOYER_PRIVATE_KEY` in the environment.
- **`scripts/deploy.ts`** deploys `StokvelVault` with admin = deployer,
  operator = Treasury Wallet, token = UCTUSD, release target = Treasury
  Wallet (D2) and `maxMembers` = 3 (DEC-3).
  - **Pre-flight checks:** settings present and valid, deployer ≠ Treasury,
    a contract exists at the UCTUSD address with 18 decimals, the deployer
    has gas, and no existing deployment record would be overwritten
    (`FORCE_REDEPLOY=1` to replace one).
  - **Post-deploy checks:** roles, token, release target, `maxMembers`,
    not paused.
  - **On testnet** it writes `deployments/xrplEvmTestnet.json` (address,
    block, tx hash, constructor arguments) and prints the
    `STOKVEL_CONTRACT_ADDRESS` line and the verify command.
  - **On the local Hardhat network** it deploys a mock token and writes
    nothing (a dry run).
- npm scripts: `deploy:local` and `deploy:testnet`.
- Local `.env` (gitignored): `DEPLOYER_ADDRESS`, `DEPLOYER_PRIVATE_KEY` and
  `EVM_TREASURY_ADDRESS`.

### Files

- `contracts/hardhat.config.ts`, `contracts/package.json`,
  `contracts/package-lock.json` (adds `dotenv`)
- `contracts/scripts/deploy.ts` (new)
- `contracts/smart_contracts_changes.md`

### Verified

- `npm run deploy:local`: deploys, and all 7 post-deploy checks pass.
- `npm run deploy:testnet` against the real testnet: connects to chain
  1449000, loads the deployer key, finds UCTUSD (`UCTUSD`, 18 decimals), then
  stops with "Deployer … has no test XRP" before sending anything.

### Acceptance criteria

- [x] The deployment script reads the deployer key from the environment
  only.
- [x] The deployer is a separate address from the Treasury Wallet
  (`0x4948b5bf3C39d63a24918de9B0346B6159f7829C`), and its key is only in the
  local `.env`. The script refuses to deploy if they match.
- [ ] Funded with test XRP (#224, Claire).
- [ ] Deploy with the UCTUSD address; operator role to the Treasury Wallet;
  admin role stays with the deployer. The script does this and checks it;
  it just needs to run.
- [ ] Verify the contract on the explorer. The command is printed after
  deploy. The Blockscout API URL in the config is the explorer's standard
  `/api` path and has not been tried yet.
- [ ] Record the contract address in doc §2 and `.env.example`
  (`STOKVEL_CONTRACT_ADDRESS`).
- [ ] **Done when:** a `contribute` call from the Treasury Wallet succeeds on
  testnet. This needs the Treasury key, which Claire holds (encrypted, #277
  and #224), so it is either run by her or by the backend once R2-02 lands.

### How to deploy (once funded)

```bash
cd contracts
npm run deploy:testnet
# then run the printed verify command, and add STOKVEL_CONTRACT_ADDRESS
```

---

## #212 DEC-1 Reconcile the contract interface (with #215 R1-01 views and #213 DEC-3 member cap)

**Date:** 2026-10-08
**Branch:** `feature/212-contract-interface-d12` (stacked on
`feature/199-pause-resume`)
**Status:** Contract and tests done (67 passing). Doc §1 not yet updated
(see "Left open").

### Why

On 2026-10-07 the team agreed doc decision D12 and a new contract interface
in `docs/stokvel_integration.md` §1, after #197–#199 were built. The
backend codes against §1, so the contract now follows it. #199, #200 and
#201 were replaced by #217, #216 and #273.

### What changed

- **Stokvels and cycles are separate.**
  `createStokvel(id, contribution)` registers a stokvel.
  `startCycle(id, memberIds, roundStartTimes, roundDeadlines, payoutTimes)`
  fixes the members (array order is the payout order) and the round
  schedule. `updateStokvel` and the single `startTime`/`interval` are gone.
  A new cycle can start once the previous one closes, which closes the old
  "no next cycle" open item from #198.
- **Payout-time gate (D12):** round N releases only when it is fully paid,
  round N+1 is fully paid (or N is the last round), **and**
  `block.timestamp >= payoutTimes[N]`. A contribution that completes the
  condition after the payout time releases in the same transaction, as
  before.
- **New external `finalise(id, round)`** (operator, `whenNotPaused`,
  `nonReentrant`) for rounds that become due with time. It releases exactly
  the requested round, which must be the next to release.
- **`contribute(id, round, memberId)` has no `amount` again,** matching
  §1. `WrongAmount` now means the vault received less than the contribution:
  it measures its balance before and after the pull.
- **`maxMembers` is a constructor argument (DEC-3):** 3 for the prototype,
  minimum 2. It replaces the `MAX_MEMBERS = 12` constant.
- **Views (R1-01):** `getStokvel`, `getCycle`, `hasPaid`, `roundPool`,
  `isFinalisable`, plus `isMember`, `paidCount` and `openRound`. All except
  `getCycle` read the current cycle.
- **Events (§1 names):** `StokvelCreated(id, contribution)`,
  `CycleStarted(id, cycle)`,
  `ContributionMade(id, cycle, round, memberId, amount)`,
  `RoundFinalised(id, cycle, round, memberId, pool)` and
  `CycleClosed(id, cycle)`. `id` and `memberId` are indexed.
- **Errors (§1 names):** `NotMember`, `AlreadyPaid`, `WrongRound`,
  `WrongAmount`, `NotYetFinalisable`, `AlreadyFinalised`, `CycleNotOpen`,
  `UnknownStokvel` and `MaxMembersExceeded`, plus input-validation errors
  (`ZeroId`, `StokvelExists`, `ZeroContribution`, `CycleInProgress`,
  `TooFewMembers`, `ZeroMemberId`, `DuplicateMember`,
  `ScheduleLengthMismatch`, `InvalidSchedule`, `UnknownCycle`,
  `InvalidMaxMembers`, `ZeroAddress`, `AdminIsOperator`).
- **IDs** are database UUIDs packed left-aligned into `bytes32`.
  `uuidToBytes32` in `test/helpers.ts` is the reference packing; the backend
  must match it.
- `startCycle` was split into the `_beginCycle` and `_validateSchedule`
  helpers to stay under the EVM's stack limit, without switching to the
  `viaIR` compiler mode.

### Files

- `contracts/src/StokvelVault.sol` (rewritten)
- `contracts/src/mocks/FeeOnTransferToken.sol` (new; for the `WrongAmount`
  test)
- `contracts/test/helpers.ts` (new; shared fixtures and `uuidToBytes32`)
- `contracts/test/StokvelVault.setup.test.ts` (new; replaces
  `StokvelVault.create.test.ts`)
- `contracts/test/StokvelVault.contribute.test.ts`,
  `StokvelVault.pause.test.ts` (rewritten)
- `contracts/test/StokvelVault.views.test.ts` (new)

### Acceptance criteria

DEC-1 (#212):
- [x] `finalise` requires the paid condition **and**
  `block.timestamp >= payoutTimes[round]`; `startCycle` takes `payoutTimes`;
  "too early" raises `NotYetFinalisable`.
- [x] `createStokvel` shape, `startCycle`, and event names now match §1.
- [ ] Update doc §1 to match the contract as built, and comment on #197 and
  #198.
- [ ] Tell Claire and Sian once §1 is stable.

R1-01 (#215):
- [x] `getStokvel`, `getCycle`, `hasPaid`, `roundPool` and `isFinalisable`,
  with a test each. The `isFinalisable` tests cover the paid condition alone,
  the time alone, and both together.
- [ ] Write their signatures into doc §1.

R1-02 (#216), the two new tests it asks for:
- [x] Finalise is rejected before the payout time even when all have paid.
- [x] A round blocked after its payout time while a member has not paid is
  then released once they pay, in the same transaction.

DEC-3 (#213), contract side:
- [x] `maxMembers` is set at deployment; 3 goes in the deploy script (#218).

### Decisions

- **The error is named `CycleNotOpen`, not `CycleClosed`.** §1 uses
  `CycleClosed` for both an event and an error, and Solidity does not allow
  one name for both. The event keeps the §1 name.
- **`cycle` was added to `ContributionMade` and `RoundFinalised`.** §1 has
  multiple cycles, but its events had no cycle number, so event sync (R2-13)
  could not tell cycles apart.
- **Start times and deadlines are stored but not enforced.** Only payout
  times are a hard gate (D7, D12). Rounds still fill in order, and members
  can pay ahead.
- **The schedule must be ordered.** Within each round, start ≤ deadline ≤
  payout. Start and payout times may not go backwards between rounds. Equal
  times are allowed. This guarantees that the round released next is always
  the earliest one due.
- **`finalise` releases exactly one round.** It must be the next round to
  release; an earlier one gives `AlreadyFinalised` and a later one
  `NotYetFinalisable`. The scheduled task calls it once per due round.
- **`isFinalisable` ignores pause** and reports only the release
  conditions. Check `paused()` separately.
- **Member IDs should be per-stokvel row UUIDs** (for example
  `stokvel_members.id`), not user IDs, so one person's stokvels cannot be
  linked on-chain. This replaces the earlier HMAC suggestion: random UUIDs
  are not guessable, and a per-stokvel row ID is not linkable.
- **Pause is unchanged:** `contribute` and `finalise` stop, while
  `createStokvel`, `startCycle` and the views keep working.

### Fix (2026-10-09): duplicate error and a payment into a round that does not exist

Branch `fix/duplicate-contribution-error`, from `main` after #282 merged.
Found by Kerry while testing.

- **Wrong error for a duplicate.** A member paying a round they had already
  paid got `WrongRound` instead of `AlreadyPaid` once that round had filled,
  because `contribute` checked the round before the duplicate. While the round
  was still filling, the error was correct, which is why the tests missed it;
  one test even asserted the wrong error. `contribute` now checks membership,
  then "already paid", then the round, so a repeat payment always reports
  `AlreadyPaid` (including into a round that has already been released). This
  matters for the demo ("a duplicate contribution is rejected") and for the
  §6 message the user sees.
- **Funds could get stuck.** Once every round of a cycle was paid but not yet
  released (waiting for payout times), `openRound` equals the member count,
  and `contribute` for that round number, which does not exist, was accepted:
  tokens went into a pool that could never be released. `contribute` now
  rejects any round at or beyond the member count with `WrongRound`. The
  contract is not deployed yet, so no funds were affected.
- **Tests:** three tests that asserted the old behaviour now expect
  `AlreadyPaid`. Two new regression tests cover a duplicate into a full round
  and into a released round, and a new check covers paying the nonexistent
  round. On `main`'s old contract these tests fail in 4 places; with the fix,
  all 69 pass. Branch coverage of `contribute` is complete.
- No interface change: the function signatures, errors and events are the
  same, so the ABI is unchanged.
- **Randomised invariant tests** (`test/StokvelVault.invariants.test.ts`).
  Both bugs came from situations nobody wrote a test for, so hand-picked
  tests are not enough on their own. 80 random runs of 60 steps, with 3 and
  2 members, mix contributions (right and wrong rounds, wrong members,
  duplicates), `finalise` calls, time jumps, pause and resume, and new
  cycles. After every step the contract must match a small reference model
  of the rules, and these must hold:
  - the vault holds exactly the unreleased pools;
  - nothing is paid into a round that does not exist;
  - each round is released once, to the right member, for the full pool.
  Seeds are fixed, so a failure can be replayed.
- **Checked that they work:**
  - On `main`'s old contract they fail at once. They also found a third
    ordering issue: a non-member paying a wrong round got `WrongRound`
    instead of `NotMember`; the new order (member first) fixes it.
  - With each bug put back into the fixed contract on its own, they catch
    each one.
  - 71 tests in total; the random suites add about 40 s.

### Left open / for later tickets

- **Doc §1 update (DEC-1 and R1-01 "done when"):** the doc lives on `main`.
  It needs the `CycleNotOpen` name, `cycle` in the two events, the extra
  validation errors, the view signatures, `maxMembers` in the constructor,
  and the `uuidToBytes32` packing.
- **Cancel and refund (#220 R1-06)** waits on #208. Any refund function
  must carry `whenNotPaused`.
- **Deploy (#218):** use constructor
  `(admin = deployer, operator = Treasury Wallet, UCTUSD
  0x7055071C7B79A859d9514e62833BFf041ce71074, releaseTarget = Treasury
  Wallet, maxMembers = 3)`.
- **Product questions still open:** P2 (legal review of the payout hold)
  and P6 (merge the deadline and payout time). If P6 merges them, the
  contract needs no change: pass the same value for both.

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
