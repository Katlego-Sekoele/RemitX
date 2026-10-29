# Stokvel test plan

Every test the class brief requires, the test or ticket that covers it, and who
owns it (R6-01, #266). The brief's list is in
[ftc_project_brief.md](ftc_project_brief.md) §7.5; §2 adds the three demo cases
and §6 sets the deadline: **all three rounds on the deployed version, the
blocked round, the rejected duplicate and early finalisation, and a passing
settlement retry test by Friday 23 October** (code freeze).

Last checked against `main` on 2026-10-19. When a ticket lands or an owner
changes, update its row here in the same PR.

**Status:** **Covered**: a test on `main` proves it. **Planned**: a ticket owns it
and can start. **Blocked**: its ticket is waiting on another one.

## Summary

| # | Brief requirement | Where | Ticket | Owner | Status |
|---|---|---|---|---|---|
| C1 | Valid contributions | Contract tests | R1-02 (#216) | Kerry | Covered |
| C2 | Valid payouts | Contract tests | R1-02 (#216) | Kerry | Covered |
| C3 | Incorrect amounts | Contract tests | R1-02 (#216) | Kerry | Covered |
| C4 | Duplicates | Contract tests | R1-02 (#216) | Kerry | Covered |
| C5 | Unauthorised senders | Contract tests | R1-02 (#216) | Kerry | Covered |
| C6 | Early or underfunded finalisation | Contract tests | R1-02 (#216) | Kerry | Covered |
| C7 | Repeated finalisation | Contract tests | R1-02 (#216) | Kerry | Covered |
| C8 | Pause | Contract tests | R1-03 (#217) | Kerry | Covered |
| C9 | Closure after round three | Contract tests | R1-02 (#216) | Kerry | Covered |
| C10 | Contract tests run in CI | `.github/workflows/ci.yml` | R5-01 (#262), #289 | Katlego | **Planned: not in CI yet** |
| S1 | A retried settlement does not repeat the release, remittance, burn or credit | `api/tests/` | R6-06 (#271), R3-06 (#243) | Mridula, Sian | **Blocked** on #241 → #242 → #243 |
| D1 | Full journey: three members, three rounds (locally and on the deployed version) | `api/tests/`, demo script | R6-04 (#269) | Mridula | **Blocked** on #243 |
| D2 | A round blocked because one member has not paid | Demo script | R6-05 (#270) | Mridula (Kerry supports) | **Blocked** on #269 |
| D3 | A duplicate contribution is rejected | Demo script | R6-05 (#270) | Mridula (Kerry supports) | Planned (the API already refuses it) |
| D4 | An early finalisation is rejected | Demo script | R6-05 (#270), R3-10 (#247) | Mridula, Katlego | **Blocked** on #247 |
| D5 | Synthetic data for the demo | Seeder story | R6-03 (#268) | Mridula | Planned |
| T1 | Demo timing: rounds a few minutes apart | Demo script, seeded schedule | R6-07 (#272), R6-03 (#268) | Mridula | Planned |

## Contract tests (brief §7.5)

All in `contracts/test/`, run with `cd contracts && npm test`. Contract tests
were done in R1-02 (#216) and the pause tests in R1-03 (#217). The randomised
invariant tests (`StokvelVault.invariants.test.ts`) also check every rule
against a reference model.

| # | Requirement | Tests that prove it |
|---|---|---|
| C1 | Valid contributions | `contribute.test.ts`: "pulls exactly the contribution and records it", "accepts a late contribution (the deadline is informational)" |
| C2 | Valid payouts | `contribute.test.ts`: "finalise succeeds once the payout time passes", "each round is released exactly once, to the right member", "when payouts are already due, contributions release as they complete" |
| C3 | Incorrect amounts | `contribute.test.ts`: "rejects a short transfer (WrongAmount) and leaves no state", "rejects when the Treasury Wallet has not approved enough". The contract pulls the stokvel's fixed contribution itself (no amount argument), so a wrong amount can only arrive as a short transfer |
| C4 | Duplicates | `contribute.test.ts`: "rejects a duplicate contribution", "a repeat payment into a round that has filled reports AlreadyPaid, not WrongRound", "a repeat payment into a released round reports AlreadyPaid" |
| C5 | Unauthorised senders | `contribute.test.ts`: "rejects an unauthorised sender", "finalise rejects an unknown stokvel, no cycle, and other callers". Also unknown members (brief §7.1): "rejects an unknown member, including one from another stokvel" |
| C6 | Early or underfunded finalisation | Early: "finalise is rejected before the payout time, even when all have paid". Underfunded: "a round one short never releases, however late", "a round blocked after its payout time stays blocked, then releases when the last member pays", "round N waits for round N+1 to fill, even after its payout time" (D5). All `contribute.test.ts` |
| C7 | Repeated finalisation | `contribute.test.ts`: "finalise only releases the next round, in order" and "after closing, contribute and finalise are rejected" (both expect `AlreadyFinalised`) |
| C8 | Pause | `pause.test.ts`: who can pause and resume; contribute and finalise revert while paused, "even for a round that is ready"; after resuming, "release conditions are unchanged: no early release"; "a full cycle completes across several pauses" |
| C9 | Closure after round three | `contribute.test.ts`: "each round is released exactly once, to the right member" (three members, three `RoundFinalised` events, one `CycleClosed`), "after closing, contribute and finalise are rejected" |

**Gap (C10):** CI doesn't run these yet. `ci.yml` has no contracts job; R5-01
(#262) and #289 (Katlego) add one. Until they land, the tests only prove
something when someone runs them locally, and a change that breaks the contract
can still merge.

## Settlement tests (brief §7.5, §7.2)

The brief: *"Retrying a failed settlement must not repeat the release, burn or
beneficiary credit."* A stokvel payout is a pool release, then a remittance with
the stokvel as sender, then the existing burn chain (doc §4, work breakdown step
4).

**Already covered on `main`, one step at a time:**

| Step | Tests |
|---|---|
| Release, on-chain | Contract: "each round is released exactly once, to the right member", plus `AlreadyFinalised` (C7) |
| Release, payout row | `api/tests/test_stokvel_payout_model.py`: `test_a_round_is_paid_out_once`, `test_a_failed_release_is_retried_on_the_same_row`, `test_two_payouts_never_share_a_leg_hash_quote_or_remittance` |
| Burn | `api/tests/test_worker_burn_treasury_tokens.py`: `test_burn_twice_does_not_double_submit`, `test_a_retry_with_a_stored_hash_waits_on_it_and_sends_nothing`, `test_nothing_is_sent_if_the_hash_cannot_be_stored` |
| Beneficiary credit | `api/tests/test_worker_burn_treasury_tokens.py`: `test_confirm_twice_does_not_double_credit`, `test_confirm_failure_twice_does_not_refail_or_change_balances` |
| Re-queuing a stuck settlement | `api/tests/test_reclaim_settlements.py`: `test_a_processing_group_with_a_burn_hash_is_never_re_enqueued`; `api/tests/test_admin_settlement_recovery.py`: `test_retry_refuses_processing_group` |
| Contributions (the step before) | `api/tests/test_worker_stokvel_contribution.py`: `test_a_redelivered_submit_waits_on_the_stored_hash_and_never_pays_twice`, `test_a_replayed_confirm_credits_nothing_twice` |

**Still to build (S1):** one test that fails a stokvel payout partway through,
retries it, and checks that nothing repeats from start to finish. It should
cover failures after the pool release but before the payout row is updated,
after the burn is sent but before its receipt, and a redelivered
`settle_remittance`. Owned by **R6-06 (#271, Mridula)**. **R3-06 (#243, Sian)**
plans `api/tests/test_stokvel_payout_retry.py` with the same goal, so agree
with Sian whether one test covers both tickets. Blocked until the payout chain
exists: R3-04 pool release (#241), R3-05 stokvel remittance (#242) and R3-06
hand-off (#243), all Sian, none started.

## Demo cases (brief §2)

The final demo must show these on the deployed version. Each one is also an
automated test, so the demo isn't the first time it runs.

| # | Case | How | Depends on |
|---|---|---|---|
| D1 | Three synthetic members across three rounds, each payout reaching the right beneficiary | R6-04 (#269): a local test with the chain stubbed (in CI) and a script against the deployed version. Round N releases only once round N+1 is fully paid and N's payout time has passed (D5, D12), so the script pays round 2 before round 1's payout appears | #243, #248 (scheduled release), #268 |
| D2 | A round blocked because one member has not paid | R6-05 (#270). Run it on its own stokvel: a blocked round stays blocked (no cancellation, #208), so it would stop the main three-round flow | #269 |
| D3 | A duplicate contribution rejected | R6-05 (#270). The API refuses a second payment to the open round (409 `contribution_already_paid`), and the contract rejects it too (C4) | none |
| D4 | An early finalisation rejected | R6-05 (#270). Finalisation is automatic (D5), so the early call comes from the admin finalise route R3-10 (#247, Katlego) behind the admin button R4-11 (#260, done). The contract refuses it (C6) | #247 |
| D5 | Synthetic data | R6-03 (#268): a seeder story with three KYC-approved, funded members, each with a beneficiary, plus a second stokvel with one invitation pending to show the lapse when the cycle starts | none |

## Demo timing (brief §7.5)

**T1:** rounds a few minutes apart. The schedule is set when the Organiser
starts the cycle (`POST /stokvels/{id}/cycles`), and the demo script in R6-07
(#272, Mridula) gives the times. The seeded stokvel (#268) is left `forming` so
the demo starts the cycle with a fresh schedule. The open question in doc §8
("Demo timing … Deferred, Role 6") closes with #272.

## Gaps and actions

| Gap | Action | Who |
|---|---|---|
| Contract tests aren't in CI (C10) | Land R5-01 (#262) / #289 before the code freeze | Katlego |
| The payout chain (#241 → #242 → #243) hasn't started, and S1, D1, D2 and most of the rehearsal wait on it | Agree dates with Sian; the code freeze is Friday 23 October | Sian, Mridula |
| S1 is planned twice (#271 and #243) | Agree one test, owned by one ticket | Mridula, Sian |
| D4 needs the admin finalise route (#247) | Land #247 so the early call can come from the admin screen; otherwise the demo calls it from a script | Katlego |
| #269–#272 have no assignee on GitHub | Assign to Mridula | Katlego |

## Out of scope

- **Cancellation and refunds:** dropped in #208, and refunds are out of scope in
  brief §9. No cancel or refund tests.
- **Recovering missed contributions and penalties** (brief §9): a blocked round
  stays blocked, which is what D2 shows.

## Running the tests

```bash
cd contracts && npm test     # C1–C9
cd api && pytest             # settlement steps above, the stokvel API and worker
cd api && TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:PORT/postgres pytest -m postgres
                             # the Postgres lane (row locks, row-level security)
```
