# Smart contracts: status review

**As of:** Fri 9 Oct 2026, the brief's deadline for "contract deployed and tested on the testnet".
**Scope:** `contracts/` on `main` (`5df4a76`) and the three open contract PRs. It is checked against
the [class brief](../docs/ftc_project_brief.md), the [integration doc](../docs/stokvel_integration.md),
the [ticket plan](../docs/stokvel_ticket_plan.md) and the per-ticket log in
[smart_contracts_changes.md](smart_contracts_changes.md).

**How this was checked:** I read the contract, the tests, the docs and the open PR branches. Then I ran:

- `npx hardhat test` on `main`: **67 passing**.
- `npx hardhat test` on `feature/219-readme-abi-adr`: **69 passing**.
- `npx hardhat coverage` on that branch: **100% lines, 99.1% branches** on `StokvelVault.sol`.
- `npm run deploy:local` on that branch: all 7 post-deploy checks pass.

---

## 1. Summary

- **The contract is built and well tested.** Code and tests are on `main` (merged in PR #282). Every
  contract rule in brief §7.1 is implemented and tested.
- **It is not deployed.** The deploy script works, but the deployer wallet has no test XRP yet (#224).
  This misses the brief's Fri 9 Oct target.
- **Three contract PRs are open and unmerged:**
  - #283: doc §1 update
  - #284: deploy script
  - #285: README, ABI export and ADR
- **On `main` the integration doc §1 is still the old draft.** It uses the wrong error name, has no
  `cycle` in the events and lists the views as TBD.
- **Nothing in the backend talks to the contract yet.** `evm_service.py` only loads keys. There is no
  `stokvel_contract.py` wrapper, no ABI loading and no `STOKVEL_CONTRACT_ADDRESS`.
- **No security bugs found.** Access control, the reentrancy guard, state-before-transfer ordering and
  pause are all correct. There are **three medium logic or design issues and several smaller ones**
  (section 6).

---

## 2. What has been done

### On `main` (merged, PR #282)

| Item | Detail |
|---|---|
| Hardhat project | Hardhat 2, Solidity 0.8.24, `evmVersion: paris`, OpenZeppelin v5, TypeScript 5.8 |
| `src/StokvelVault.sol` | One contract holds every stokvel (D4). See the next table |
| Roles | `DEFAULT_ADMIN_ROLE` can pause and resume. `OPERATOR_ROLE` (Treasury Wallet) can create, start a cycle, contribute and finalise. The constructor rejects admin == operator |
| Functions | `createStokvel(id, contribution)`, `startCycle(id, members, starts, deadlines, payouts)`, `contribute(id, round, memberId)`, `finalise(id, round)`, `pause()`, `unpause()` |
| Release rule | Round N releases when (a) round N is fully paid, (b) round N+1 is fully paid or N is the last round, and (c) `block.timestamp >= payoutTimes[N]` (D5, D12). It releases automatically inside `contribute`, or through `finalise` |
| Views | `getStokvel`, `getCycle`, `hasPaid`, `roundPool`, `isFinalisable`, `isMember`, `paidCount`, `openRound`, `paused` |
| Events | `StokvelCreated`, `CycleStarted`, `ContributionMade(…cycle…)`, `RoundFinalised(…cycle…)`, `CycleClosed`, plus OpenZeppelin's `Paused` and `Unpaused` |
| Errors | The 9 errors from doc §1 (with `CycleClosed` renamed `CycleNotOpen`), plus 13 input-validation errors |
| Multi-cycle | A new cycle (with new members and order) can start once the previous one closes |
| Safety | `SafeERC20`; the vault measures its balance before and after each pull (`WrongAmount`); state changes before every transfer; `nonReentrant`; `whenNotPaused` on everything that moves tokens |
| Test mocks | `MockUCTUSD`, `ReentrantToken`, `FeeOnTransferToken` (never deployed) |
| Tests (67) | Setup (21), contribute and release (27), pause (10), views (9) |
| Change log | `smart_contracts_changes.md`: one entry each for #197, #198, #199 and #212 |

### In open PRs (not merged)

| PR | Branch | Adds | Status |
|---|---|---|---|
| #283 | `docs/212-contract-interface-section-1` | Doc §1 rewritten to match the contract: constructor, signatures, errors, events, views and the Treasury allowance rule. Updates §2 (wallet addresses), §6, §9, §13 and §14 | Open. Has stale PR references (see 6.2) |
| #284 | `feature/218-deploy-testnet` | `hardhat.config.ts` network and explorer settings; `scripts/deploy.ts` with pre-flight and post-deploy checks; `deploy:local` and `deploy:testnet` scripts | Open. Dry run passes. Testnet run stops at "deployer has no test XRP" |
| #285 | `feature/219-readme-abi-adr` (stacked on #284) | `contracts/README.md` (trust assumption), `abi/StokvelVault.json` and an ABI drift test, `scripts/export-abi.js`, `docs/adr/0002-one-contract-many-stokvels.md`, 2 coverage tests | Open. 69 tests, 99.1% branch coverage |

**Merge note:** #284 and #285 are based on an older `main`. Their diff against today's `main` shows
docs, infra and `api/` files being deleted. That is only because the branches are behind `main`, not
a real change, but rebase both before merging so nothing is reverted by accident.

---

## 3. Tickets

| Ticket | Issue | Covered | Not covered |
|---|---|---|---|
| Stokvels and cycles | #197 | Done (replaced by the #212 design) | — |
| Contributions and finalisation | #198 | Done | — |
| R1-03 Pause and resume | #217 (was #199) | Contract part done and tested | Backend route (R3-07, #244) and admin control (R4-07, #256) not started. "Backend refuses to submit while paused" not done |
| D1 Reconcile the interface | #212 | Contract matches the decided interface and D12 | Doc §1 update is in PR #283, not merged. Comments on #197 and #198 not confirmed |
| D3 Member cap | #213 | `maxMembers` is a constructor argument; the deploy script defaults to 3 | Backend `MAX_STOKVEL_MEMBERS` is not in `config.py` or `.env.example` |
| R1-01 Views | #215 | All five views plus three extras, each with a test | Signatures in the doc: PR #283, not merged |
| R1-02 Contract tests | #216 | Every brief §7.5 contract case, plus both payout-time tests the ticket asks for | 2 coverage tests only in PR #285. No property-based tests. Scripts not tested automatically |
| R1-04 Deploy | #218 | Script written and dry-run tested (PR #284) | **Not deployed** (needs #224 funding). Not verified on the explorer. Address not in doc §2 or `.env.example`. Testnet `contribute` not tried |
| R1-05 README, ABI, ADR | #219 | All done in PR #285 | Not merged |
| R1-06 Cancel and refund | #220 | — | Dropped: #208 decided cancellation and refunds are out of scope (ADR 0003, 2026-10-09). Nothing to build |
| R1-07 Burn method | #265 (Mridula) | — | Doc §8 still open. Blocks #278 (burn) |
| R5-01 Contracts CI job | #262 (Katlego) | — | No `contracts` job in `.github/workflows/ci.yml` on any branch |
| Backend connection | #273, #222 | `evm_service.py` loads the Treasury key (PR #211, merged) | No contract wrapper, ABI loading, `approve`, `contribute` call or state reads |

### Open issues from the ticket plan (OI-1 to OI-5)

| OI | Contract side | Still open |
|---|---|---|
| OI-1 Who calls `finalise` | Settled in the contract: `contribute` releases automatically when it can, and `finalise` handles rounds that become due with time | Doc §4 still says `confirm_contribution` queues `release_pool`. When `contribute` has already released the round, `release_pool` will get `AlreadyFinalised` and must treat that as success. The `STOKVEL` ledger credit must come from the `RoundFinalised` event, not from the task that sent the transaction |
| OI-2 ERC-20 approval | Decided (one `approve(max)` per contract address, checked before each `contribute`). Written in the README and PR #283 | Nobody has run the approval yet. No backend code |
| OI-3 Wrapper dependency | n/a | Plan edit not made |
| OI-4 Pause check | `paused()` view exists | Not assigned to a backend ticket |
| OI-5 Contribution amount | Contract fixes the amount once per stokvel, for every cycle | Doc §1 and §3 on `main` still say "locked at cycle start" (see 6.1 #3) |

---

## 4. Brief coverage

### §7.1 Smart contract

| Requirement | Status | Where |
|---|---|---|
| Configure one stokvel: 3 member IDs, fixed contribution, payout time per round, payout order | ✅ Generalised to many stokvels, 2 to `maxMembers` members, and repeat cycles | `createStokvel`, `startCycle` |
| Accept UCTUSD contributions from the backend, recorded against member and round | ✅ | `contribute` |
| Reject incorrect amounts | ⚠️ Partial (see note below) | `WrongAmount` |
| Reject duplicates, unknown members, unauthorised senders | ✅ (but see 6.1 #1 on which error a duplicate gets) | `AlreadyPaid`, `NotMember`, `AccessControlUnauthorizedAccount` |
| Finalise only when all have paid and the payout time has passed | ✅ Stricter than the brief: it also waits for round N+1 (P2, see 6.1 #6) | `_isFinalisable` |
| Transfer the pool to the settlement wallet, record the entitled member, advance the round | ✅ The entitled member is in `RoundFinalised` and `members[round]` | `_release` |
| A round cannot be finalised twice | ✅ | `AlreadyFinalised` |
| Emit contribution and payout events | ✅ | `ContributionMade`, `RoundFinalised` |
| Close the cycle after round three | ✅ | `CycleClosed` |
| Admin pause and resume without bypassing payout conditions | ✅ Tested across long pauses and repeated pause and resume | `pause`, `unpause` |
| OpenZeppelin for tokens, access control, pausing, reentrancy | ✅ | `SafeERC20`, `AccessControl`, `Pausable`, `ReentrancyGuard` |

**Note on incorrect amounts:** `contribute` has no amount argument, so the backend cannot send a wrong
amount. `WrongAmount` only fires if the vault receives less than the contribution. That is tested with
a fee-on-transfer token, and a short allowance is tested too. A marker looking for "submit a wrong
amount, see a revert" will not find that test. Explain this in the README or the demo.

### §7.4 Security and data

| Requirement | Status |
|---|---|
| Personal data off-chain; contract stores member IDs only | ✅ Opaque per-stokvel row UUIDs packed into `bytes32` |
| Protect admin functions | ✅ Role-gated; admin ≠ operator at deployment |
| Document that the contract relies on the backend to identify the member | ✅ In NatSpec on `main`, and in the README in PR #285 (not merged) |
| Keys never in source control | ✅ The deploy key is read from `.env` only |

### §7.5 Contract tests

| Required test | Status |
|---|---|
| Valid contributions and payouts | ✅ |
| Incorrect amounts | ⚠️ Fee-on-transfer and allowance only (see note above) |
| Duplicates | ✅ |
| Unauthorised senders | ✅ |
| Early or underfunded finalisation | ✅ Before the payout time, one member short, next round not paid |
| Repeated finalisation | ✅ |
| Pause | ✅ |
| Closure after round three | ✅ Also tested with 2 and 12 members |

### §2 Demo needs (contract side)

| Demo item | Status |
|---|---|
| 3 members × 3 rounds | ✅ In tests. Not yet on testnet |
| Round blocked because one member has not paid | ✅ |
| Duplicate contribution rejected | ⚠️ Rejected, but with `WrongRound` once the round is full (6.1 #1) |
| Early finalisation rejected | ✅ `NotYetFinalisable` |

### §6 Timeline

| Target | Status |
|---|---|
| Fri 9 Oct: contract deployed and tested on testnet | ❌ Tested locally only. Not deployed (#224) |
| Fri 9 Oct: backend stores the key, connects with web3.py, can submit a contribution and read state | ❌ Key storage done (PR #211). No contract calls yet |

### §9 Out of scope, but built anyway

Multiple stokvels, multiple cycles and automated release are built. All are recorded as deviations
(D3, D4, D5).

---

## 5. Integration doc coverage

| Section | Covered | Not covered |
|---|---|---|
| Decisions D2, D4, D5, D7, D12 | Implemented in the contract | — |
| P2 Payout hold | Implemented | Still "Proposed, needs legal review" (6.1 #6) |
| P3 Member cap | `maxMembers` set at deployment | Backend config value |
| P4 Cancellation | — | Rejected, out of scope (#208, ADR 0003) |
| P5 Admin finalise fallback | `finalise` is callable by the operator | Admin route R3-10 |
| P6 Merge deadline and payout time | No contract change needed: pass the same value twice | Product decision |
| §1 Units and IDs | `uuidToBytes32` reference in `test/helpers.ts` | Backend helper. "Locked at cycle start" on `main` is wrong (6.1 #3) |
| §1 Roles | ✅ | — (`refund` removed from the doc with P4) |
| §1 Functions | `createStokvel`, `startCycle`, `contribute`, `finalise`, `pause`, `unpause` | — (`cancel`, `refund` removed from the doc with P4) |
| §1 Errors | All except the renamed `CycleClosed` → `CycleNotOpen` | Doc on `main` not updated (PR #283) |
| §1 Events | All events; `cycle` added to two of them | Doc on `main` lacks `cycle` and `StokvelCreated` (PR #283) |
| §1 Views | All built | Still "TBD" on `main` (PR #283) |
| §2 Network and addresses | Network settings in `hardhat.config.ts` (PR #284). Wallet addresses in PR #283 | **Contract address TBD.** `STOKVEL_CONTRACT_ADDRESS` and `MAX_STOKVEL_MEMBERS` are missing from `.env.example`. `DEPLOYER_PRIVATE_KEY` is not documented in `.env.example` |
| §3 Idempotency (contract side) | `AlreadyPaid` and `AlreadyFinalised` back the DB guards | — |
| §4 Event → DB | Every event the sync needs exists, with `id` and `memberId` indexed | The table doesn't list `StokvelCreated` or `CycleStarted`. |
| §6 Error mapping | Main errors mapped | On `main` it still says `CycleClosed`. No mapping for `UnknownStokvel`, `CycleInProgress`, `TooFewMembers`, `DuplicateMember`, `InvalidSchedule`, `AccessControlUnauthorizedAccount`, or the allowance error (PR #283 adds the last one) |
| §9 Progress | — | On `main` the contract rows say "Not started". PR #283 updates them but cites the wrong PRs |
| §13, §14 Files and functions | — | Empty on `main`. Filled in PR #283 |

---

## 6. Bugs and logic inconsistencies

No exploitable bugs were found. The reentrancy, access-control, pause and overflow paths are all
correct and tested. The `uint8` round arithmetic cannot overflow: `round < n ≤ 255` is always checked
before `round + 1`. The issues below are logic and design gaps, most serious first.

### 6.1 Contract

**1. A duplicate contribution gets `WrongRound`, not `AlreadyPaid`, once the round is full (medium, affects the demo).**

- **Cause:** `contribute` checks `round != openRound` before it checks `_paid`
  ([StokvelVault.sol:225-230](src/StokvelVault.sol#L225-L230)). Once every member has paid round 0, the
  open round is 1. A second payment for round 0 then fails with `WrongRound(0, 1)`. The existing test
  expects exactly this ([contribute.test.ts:119-121](test/StokvelVault.contribute.test.ts#L119-L121)).
- **Effect:** `AlreadyPaid` only shows up while the round is still filling. Through the §6 mapping, the
  brief's "duplicate contribution rejected" demo would show "This round isn't open for contributions"
  instead of "You've already paid for this round".
- **Fix:** in `contribute`, check `_paid[id][cycle][round][memberId]` (for any round up to the open
  round) before the open-round check. Alternatively, have the backend map a `WrongRound` on an
  already-paid round to `contribution_already_paid`. Either way, script the demo duplicate while the
  round is still open.

**2. `releaseTarget` is immutable, but the operator role can be rotated (medium).**

- **Cause:** pools always go to `releaseTarget`, which is fixed in the constructor
  ([StokvelVault.sol:56](src/StokvelVault.sol#L56)). The admin can move `OPERATOR_ROLE` to a new
  Treasury Wallet, and a test shows this as a supported operation
  ([setup.test.ts:336](test/StokvelVault.setup.test.ts#L336)).
- **Effect:** after a rotation, for example because the Treasury key leaked, the contract keeps
  sending released pools to the **old** wallet. The only fix is a redeploy, and stokvels in progress
  cannot move to the new contract (ADR 0002).
- **Fix:** add an admin-only `setReleaseTarget`, with an event. Or document that rotating the Treasury
  means a redeploy, and drop the rotation test's implied use.

**3. The contribution is fixed per stokvel, but the docs say it is locked per cycle (medium, design).**

- **Cause:** `contribution` is set once in `createStokvel` and used for every cycle. No function can
  change it.
- **Conflict with the docs:** doc §1 on `main` says "locked at cycle start"
  ([stokvel_integration.md:99](../docs/stokvel_integration.md#L99)), and §3 has a per-cycle
  `stokvel_cycles.token_contribution_amount` ([line 211](../docs/stokvel_integration.md#L211)).
- **Where it stands:** PR #285's log says Claire accepted the fixed amount and will fix §3, R2-10 and
  OI-5. But OI-5 and D4 (fixed token amount or fixed fiat amount) are still open with product.
- **Risk:** if product picks a fixed **fiat** amount, the token amount has to change between cycles
  when rates move. The contract cannot do that. The only workaround is a new stokvel ID, which loses
  the history.
- **Fix:** settle D4 before the backend builds on either model. If needed, take the contribution as a
  `startCycle` argument and store it per cycle.

**4. There is no way out of a stuck cycle, and no way to recover funds (medium, known risk).**

- **A defaulting member stops the stokvel for good.** A member who never pays locks that round's pool
  in the vault. Because the cycle never closes, `startCycle` reverts with `CycleInProgress`
  ([StokvelVault.sol:403-405](src/StokvelVault.sol#L403-L405)). That stokvel ID can never run again.
- **Stray tokens are lost.** Tokens sent straight to the vault (not through `contribute`) can never
  leave it.
- **Pause has no fallback.** If the contract stays paused, all funds stay locked.
- **Status:** accepted. #208 decided on 2026-10-09 that cancellation and refunds are out of scope
  (ADR 0003), and #220 is dropped. A stuck round's pool stays locked in the vault, and that stokvel
  cannot run again; members start a new one. A possible future cancel and refund path is in the
  product file, "Future extension: cancellation and refunds".

**5. Start times are not enforced, so members can pay ahead or be blocked (low, integration).**

- **Pay ahead:** start times are informational, so a whole cycle can be paid in seconds. The test
  "with every round paid but none due" shows this.
- **Blocked:** because rounds fill in order, nobody can pay round N+1 while anyone still owes round N.
- **Backend must handle both:**
  - Enforce start times itself, if pay-ahead is not wanted.
  - Check `openRound` **before** debiting a member's fiat. Otherwise the fiat is debited and then the
    on-chain call reverts with `WrongRound`, which leaves a debit to reverse.

**6. The payout hold (P2) is built but not approved (medium, process).**

- **Cause:** brief §7.1 releases round N when round N is fully paid and its payout time has passed.
  The contract also waits for round N+1 to be fully paid. P2 is still "Proposed, needs legal review".
- **If P2 is rejected:** the contract needs a change, a full re-test and a redeploy.
- **Demo effect:** the round 0 payout waits for round 1 contributions. The last contribution releases
  rounds 1 and 2 together. The demo script should expect this.

**7. Most views only read the current cycle (low).**

- `hasPaid`, `roundPool`, `paidCount` and `isMember` read only the latest cycle
  ([StokvelVault.sol:324-349](src/StokvelVault.sol#L324-L349)).
- Once cycle 2 starts, cycle 1's paid state can't be queried, so reconciliation (R3-08) and event sync
  (R2-13) must use events for past cycles.
- A read that races a `startCycle` call gets the new cycle.
- **Fix:** add cycle-aware variants if R3-08 needs them.

**8. Schedule checks allow a disabled payout gate (low).**

- `_validateSchedule` ([StokvelVault.sol:376-393](src/StokvelVault.sol#L376-L393)) does not require
  times to be in the future or above zero. An all-zero schedule passes, which turns the D12 payout gate
  off for that cycle.
- Deadlines may also go backwards between rounds.
- This is operator-trusted, but a cheap `payouts[0] >= block.timestamp` check would catch a backend
  bug.

**9. Out-of-range `finalise` gives an unclear error (cosmetic).** `finalise(id, 7)` on a 3-member
cycle reverts `NotYetFinalisable(7)`. A range error would be clearer for the admin route (R3-10).

### 6.2 Docs and process

| # | Inconsistency | Fix |
|---|---|---|
| a | Doc §1 and §6 on `main` contradict the merged contract: the `CycleClosed` error, events without `cycle`, views TBD, contribution "locked at cycle start". The backend is told to code against this doc | Merge PR #283 |
| b | PR #283 says the contract is "In review" in PRs #279, #280 and #281, and lists files as "Added in #279". Those PRs were **closed**; the code went in through **#282** (merged). It also says 67 tests; #285 has 69 | Fix the PR references and test count in #283 |
| c | Doc §9 on `main` says contract work is "Not started" | Covered by #283 once (b) is fixed |
| d | #284 and #285 are based on an old `main`; their diff shows docs, `api/` and infra deletions | Rebase both before merging |
| e | Doc §4 lists `release_pool` as queued by `confirm_contribution`, and doesn't cover the case where `contribute` already released the round (OI-1) | Write the agreed flow into §4: the event drives the ledger credit, and `AlreadyFinalised` counts as done |
| f | `smart_contracts_changes.md` #197 entry: "Citation unverified: brief §7.4" is now resolved (`ftc_project_brief.md` §7.4 exists). The HMAC member-ID rule there was replaced by row UUIDs in #212, but the #197 entry isn't marked as replaced. The #199 entry's "69 in total" reads oddly next to #212's "67" | Add a short "superseded" note to the #197 entry |
| g | The ticket plan names `contracts/src/Stokvel.sol` and `abi/Stokvel.json`; the real files are `StokvelVault.sol` and `abi/StokvelVault.json` | Update the plan's file lists (R1-02 to R1-06, R3-07, R3-10) |
| h | `.env.example` lacks `STOKVEL_CONTRACT_ADDRESS` and `MAX_STOKVEL_MEMBERS`, which doc §2 lists | Add them with the deploy (#218) |

---

## 7. Next steps, in order

1. **Fund the deployer (#224) and deploy (#218).** Run `npm run deploy:testnet`, verify on the
   explorer, then record the address in doc §2 and `.env.example`. Then do the Treasury `approve(max)`
   and one testnet `contribute`.
2. **Merge PR #283 (with fix 6.2 b), then rebase and merge #284 and #285.**
3. **Decide 6.1 #1 (duplicate error order) before the demo script is written.** It is a two-line
   contract change and should land before the deployment you keep.
4. **Decide 6.1 #2 (`setReleaseTarget`) and 6.1 #3 (D4, contribution per stokvel or per cycle) before
   deploying.** Both are cheap now and need a redeploy later.
5. **Add the contracts CI job (R5-01, #262).**
6. **Get product and legal answers on P2.** P4 is decided (#208: out of scope), so the stuck-cycle
   risk (6.1 #4) is accepted.
