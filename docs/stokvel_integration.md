# Stokvel Integration

This file keeps track of the process of implementing the Stokvel integration into the RemitX platform: the features added, how the pieces are connected, the user flow, and the files and functions created along the way. It is the shared contract between the six roles: everything one person builds that another person's code depends on. If someone's Claude session needs a function name, a status value or an API shape, it should come from here, not be invented.

Terminology follows [CONTEXT.md](../CONTEXT.md). Architectural decisions are recorded in [docs/adr/](adr/). The class brief is [ftc_project_brief.md](ftc_project_brief.md). The database model (section 3) is in [stokvel_database_model.md](stokvel_database_model.md), and the changelog is in [stokvel_changelog.md](stokvel_changelog.md).

## Ownership and change rule

| Section | Owner |
|---|---|
| 1. Contract interface | 1 |
| 2. Network and addresses |  1 |
| 3. Database model ([stokvel_database_model.md](stokvel_database_model.md)) |  2 and 3 |
| 4. Worker tasks |  2 and 3 |
| 5. REST API |  2, 3 and 4 |
| 6. Error mapping |  1, 2 and 4 |
| 7. TrustMeBank touchpoints |  5 |
| 8. Open questions | All |
| 9–14. Progress, features, flow, files, functions | Whoever makes the change |
| Decisions, Proposals, Deviations, EVM switch-over | All (changes via PR) |

**Change rule:** any change to an interface in this file goes through a PR approved by the owners it affects. No one changes an interface quietly inside a feature PR.

## Changelog

| Date | Section | Change | PR |
|---|---|---|---|
| 2026-10-05 | all | File created with section skeleton | |
| 2026-10-06 | all | Added Decisions, Proposals, Deviations, EVM switch-over, work breakdown; drafted sections 1–8 and 11–12 from CONTEXT.md, GitHub issues #197–#209 and earlier design sessions | |
| 2026-10-07 | Proposals, Deviations, 1, 5, 6 | Added P5: manual admin finalise as a fallback to automatic finalisation (route `POST /admin/stokvels/{id}/rounds/{n}/finalise`) | |
| 2026-10-19 | Proposals, 8, 13 | Admin manual release (R4-11 #260) on mocks until R3-10 (#247): an admin Stokvels → Rounds page lists each stokvel's current round (recipient, paid, payout time, status: waiting, release in progress, release failed, released) with a Release payout button that asks first and shows section 6's "This round can't be paid out yet." or "This round has already been paid out." when refused. P5 approved (product, Sian, 2026-10-19: keep an admin Release payout button as a fallback). Assumes `POST /admin/stokvels/{id}/rounds/{n}/finalise`; no admin route lists stokvels and rounds yet, to agree with Role 3 (#247) | #260 |
| 2026-10-07 | 3, 8, 9 | Synced with the product deviations file: recommend keeping the ledger status names; contribution amount, fees (with the fee-to-fiat suggestion), deadline, limits and key storage listed as product confirmations; Treasury Wallet created | |
| 2026-10-07 | Decisions, 8 | D1 records lecturer approval of the EVM move (Marc). Added open question: are the fee and margin converted back to fiat | |
| 2026-10-07 | 9 | GitHub issues recreated from the ticket plan: #199–#206 and #209 closed and replaced (#217, #216, #273–#278, #229); #207 and #208 kept; mapping in the ticket plan ("GitHub issues") | |
| 2026-10-07 | 7, 9, Deviations | TrustMeBank deposits and withdrawals (#202, #203) are now required, not optional | |
| 2026-10-07 | 3, 4, 5, 8, 9 | Review fixes: P2 now mentions the payout time; P5 listed before P6; `stokvel_sync_state` added to section 3; pause and cancel take a `reason`; section 9 records PR #211 (#205 and part of #204); added an open question on log redaction hiding transaction hashes | |
| 2026-10-07 | 5, 8, 9 | Added the stokvel audit log of admin actions (section 5): new audit actions and subjects on the existing `audit_log`, viewed through `GET /admin/audit` | |
| 2026-10-19 | 5, 13 | Admin audit page stokvel view (R4-12 #261): an Area filter (`subject_type=stokvel` or `stokvel_contract`, one per request, so each view writes one `audit.log.viewed`), the three stokvel admin actions in the action filter, and an explorer link for any EVM transaction hash an entry records. No backend change: `GET /admin/audit` already filters by `subject_type`, so the suggested `action_prefix` isn't needed | #261 |
| 2026-10-07 | Decisions, Proposals, 1, 3, 4, 8, 11, 12 | D5 amended and D12 added: a round is released only when it is fully paid **and** its payout time has passed (Organiser-set); a scheduled backend task releases due rounds. Deadline stays informational. Added P6 (merge deadline and payout time) | |
| 2026-10-08 | 1, 2, 6, 9, 13, 14 | Section 1 confirmed against the contract as built (DEC-1 #212, R1-01 #215): constructor and deployment arguments, final signatures, `cycle` added to `ContributionMade` and `RoundFinalised`, error `CycleClosed` renamed `CycleNotOpen` (name clash with the event), input-validation errors, view signatures, member IDs are per-stokvel row UUIDs. Cancel and refund marked planned (#220). Section 2: deployer and Treasury Wallet addresses. Section 6: error rename. Sections 9, 13, 14: contract progress, files and functions | |
| 2026-10-08 | 1, 6 | Treasury allowance agreed with the backend: one-off `approve(vault, max)` per contract address, checked before each `contribute` and re-approved if low. Section 6 maps the token's `ERC20InsufficientAllowance` to a backend 500. Backend confirmed sections 1 and 6, and the fixed contribution amount in `createStokvel` | |
| 2026-10-09 | 1 | MVP decision: the contribution amount is fixed per stokvel for all cycles; a new amount means a new stokvel | |
| 2026-10-15 | 9, 13 | Frontend scaffold (R4-02 #251): `app/stokvels`, `app/stokvels/:stokvelId` and `admin/stokvel-contract` routes, sidebar entries, and mocked responses shaped like §3 and §5 behind `lib/stokvels.ts`. The R4-01 screen list (13 screens) is on #250 | #251 |
| 2026-10-19 | 8, 13 | Create wizard (R4-03 #252), matched to R2-07 as built: name → amount → review, sending exactly `{ name, currency, contribution_amount }` with the generated client. The Organiser types the amount in the Stokvel currency; the wizard converts it to UCTUSD at the quote preview's live rate, rounded to the cent (section 8). The preview shows each member's fee share paid on top and the full pool reaching the beneficiary (D6). Member count and schedule are not chosen at creation (section 8, round schedule). The list reads `GET /stokvels` | #252 |
| 2026-10-16 | 8 | Product answers to Karabo's screen questions (via Sian): the payout goes to the member's chosen beneficiary (as #293); invite by RemitX account reference, with no WhatsApp share button before the MVP; wizard hint "Your account is charged at the live rate at the moment you pay."; keep the sidebar (no bottom tabs). Fees on top is recorded in D6 (#340) | |
| 2026-10-19 | 6, 13 | Stokvel page and contribute flow (R4-05 #254): pot ring, Pay now → confirm sheet → confirming → paid, the current round's payout tracker, payout order, members and round history. Pay now calls `POST /stokvels/{id}/contributions` (#233); the detail read stays mocked until #236. Fees on top (D6): the sheet shows an estimated fee share before paying (the quote preview on the pool, split and rounded up like `contribution_fee_share`) and the API's `fee_amount` after; the low-balance check covers both. Codes are read from `ErrorResponse.code`, including #232's `cycle_starting` (retryable). A hash is shown as proof only once its contribution is confirmed or its release is `released` (section 3); a failed release shows as failed, without promising a retry | #254 |
| 2026-10-09 | 2, 8, 9, 10, 13, 14 | Contract work brought up to date: section 2 lists the deploy script's settings and `DEPLOYER_PRIVATE_KEY` (local only); section 8 resolves the contract side of the contribution amount and the Treasury allowance, defers per-cycle amounts, and adds the admin-key question for pause (#244); section 9 marks the contract, tests and pause done (PR #282 merged), deployment in progress (#284) and README/ABI/ADR in review (#285); sections 10, 13 and 14 list the contract features, files and scripts | |
| 2026-10-09 | 1 | Error precedence: `AlreadyPaid` is checked before `WrongRound` (a repeat payment always reports `AlreadyPaid`), and a round beyond the last is rejected (fix in branch `fix/duplicate-contribution-error`) | |
| 2026-10-09 | 9, 13 | Contract tests: randomised invariant tests added (fix branch); 73 tests once the open PRs merge | |
| 2026-10-09 | 1, 2, 6, 8, 9, 10, 13, 14 | Review fixes on #283: error order marked *pending #291* (on main a repeat payment into a filled round still reports `WrongRound`, and a nonexistent round is accepted); files and features from #284, #285 and the fix branch marked "not on main yet"; ID scheme added as an open question (Katlego's review) and flagged in section 1; `CycleNotOpen` maps to neutral `cycle_not_open`; `ERC20InsufficientBalance` mapped (Treasury out of UCTUSD); UCTUSD checked on testnet: re-approve from non-zero is fine, and `burn(uint256)` works from the Treasury (answers the burn-method question, to confirm on #278) | |
| 2026-10-09 | 1, 9, 13 | #291 merged: section 1 error order is now what `main` does (pending markers removed); tests 71 on `main` | |
| 2026-10-09 | 2, 9, 13 | Contract deployed: `StokvelVault` at `0x2f240705314BB79780522635eA47d20072CB8Fe1` (block 8995825), verified on Sourcify; deployment record and `STOKVEL_CONTRACT_ADDRESS` in PR #284; smoke test from the Treasury pending | |
| 2026-10-19 | 5, 13 | Admin pause and resume (R4-07 #256) on mocks until R3-07 (#244): the contract card shows Running or Paused (since when, and why), Pause asks for a reason (10 to 500 characters, for the audit log) and says what stops, Resume asks to confirm. Assumes `POST /admin/stokvel-contract/pause` with `{ reason }`, `POST /admin/stokvel-contract/unpause`, and `paused_at` and `paused_reason` on the contract read. Notes for #244 from the contract review (Kerry): the contract's `Paused` / `Unpaused` events carry no time or reason, so `paused_at` and `paused_reason` must come from the backend's own record (the audit log, #249); and until the API refuses contributions with 503 `stokvel_paused` while paused (OI-4), a member can still submit one, which the worker (#234) retries and then fails. Resuming releases nothing by itself: a due round goes out with the next contribution or the scheduled release (#248) | #256 |
| 2026-10-09 | 2 | `DEPLOYER_PRIVATE_KEY`: listed in `.env.example` as a commented, empty placeholder (#284); the value stays in the deployer's local `.env` | |
| 2026-10-09 | 2 | Deployer key moved to `contracts/.env` so docker compose does not load it into the API and worker containers (#284) | |
| 2026-10-09 | 1, 8 | Backend review (Role 2): section 1 notes that UCTUSD's `ERC20InsufficientAllowance` / `ERC20InsufficientBalance` are not in the vault ABI (selectors given; decode with OpenZeppelin's ERC20 errors); ID scheme: backend agrees on packed UUID for the MVP, pending Marc | |
| 2026-10-09 | 2, 9, 10, 13, 14 | #283 and #284 merged; with #285, the README, ABI and ADR land too, so the "not on main yet" markers are removed and the contract rows are Done (deployment: smoke test pending) | |
| 2026-10-09 | 2 | Deploy script (Claire's #285 review): records the address before the post-deploy checks; blank settings fall back to defaults; `FORCE_REDEPLOY` documented | |
| 2026-10-09 | Proposals, 3, 5, 8, 9, 13, 14 | R2-04 (#226): `stokvels`, `stokvel_members` and `stokvel_invitations` built with row-level security (section 3). Product: fixed fiat contribution for the stokvel's life; cancellation, refunds and disputes not in v1 (P4); members and invitees see a stokvel's invitations; former members keep their history. Dropped `max_members` and `stokvels.status`; `current_cycle_id` moves to R2-05, `account_id` to R3-01; invitations can be revoked. New tickets: #297 (revoke route), #298 (rate difference), #299 (invitations screen) | #300 |
| 2026-10-11 | Decisions, 3, 8, 11 | Product: contribution amount is **fixed token** (UCTUSD), not fixed fiat. `stokvels.contribution_amount` is that UCTUSD amount; member fiat debit = amount × live rate at contribution. D13. Closes #298 (rate-difference booking was only needed under fixed fiat) | #300 |
| 2026-10-11 | 3, 8, 9, 13, 14, EVM switch-over | R3-01 (#238) and R3-02 (#239) built. Each stokvel gets a `STOKVEL` ledger account; new transaction types `stokvel_contribution` and `stokvel_pool_release` (no `stokvel_refund`: refunds are not in v1); a quote's sender can be a stokvel; `xrpl_tx_hash` becomes `evm_tx_hash` (not `onchain_tx_hash` as first planned) and the treasury becomes `REMITX_EVM_WALLET`. Details in section 3, "Ledger changes"; ADR 0004. Two follow-ups added to section 8 | #301 |
| 2026-10-12 | 3, 14 | `stokvels.deactivated_at` (null while in service). Membership `account_id` must be the member's fiat account in the stokvel currency | #300 |
| 2026-10-13 | 3, 14 | Made stokvel RLS helper and validation functions Neon-compatible: hardened `SECURITY DEFINER` functions replace unsupported custom-GUC function settings while preserving recursive-policy avoidance; PostgreSQL regression coverage added | |
| 2026-10-13 | 3, 8, 13 | Fix: a payout from a stokvel no longer goes missing from the recipient's transfers, transfer page and dashboard, or from the admin totals (the reads used to drop any quote without a sender user). Section 8: proposal for how members see their stokvel's payouts (pending roles 2 and 3), and two new questions: what former members see, and what sender name the recipient sees | #301 |
| 2026-10-14 | Decisions, 8, 11 | Fee timing is now an open product question: from the pool at payout, or on top of each contribution (product question 4 in `docs/stokvel-product-questions.md`). D6 and section 11 call "from the pool" the current plan, not a decision. Blocks R3-05 (#242) | #301 |
| 2026-10-14 | 11 | `Transaction_Flow_Context.md` is frozen as the original RemitX project's record, so it is no longer on the EVM switch-over list. Notice added to it and to CLAUDE.md | #301 |
| 2026-10-14 | 3, 8, 9, 13, 14 | R2-05 (#227): `stokvel_cycles`, `stokvel_rounds` and `stokvel_cycle_members` built with row-level security, plus `stokvels.current_cycle_id`. Rounds and payout positions are 0-based like the contract. No `token_contribution_amount` on cycles (the amount is `stokvels.contribution_amount`, D13). #293 decided: the stokvel pays the member's chosen beneficiary directly, so `payout_beneficiary_id` and `payout_currency` are firm | |
| 2026-10-14 | Decisions, 5, 12 | D3: the members agree the payout order off the platform; the Organiser only enters it. The platform does not assign the order (no automatic ordering, e.g. by acceptance time). CONTEXT.md "Payout order" updated to match | |
| 2026-10-14 | 14 | Renamed the cycle repository reads to `get_open_cycle`, `get_cycle_rounds`, `get_cycle_members` | |
| 2026-10-14 | Decisions, 9, EVM switch-over | D11 now covers code too: XRPL files, scripts and the `xrpl-py` package are kept and marked as no longer used, the same as the XRPL settings already were. Only change what EVM needs, so we can switch back to XRPL easily. D1 and the switch-over rows for `xrpl_service.py`, the wallet script and `pyproject.toml` now say "keep" instead of "replace" | #301 |
| 2026-10-14 | 3, 9, 13, 14 | #278: settlement burns UCTUSD on the XRPL EVM chain with `burn(uint256)` from the Treasury (`evm_service.burn_tokens`), exactly the `token_burn` leg's amount. The burn hash is now stored before the send, so only a `confirmed` leg's hash proves a burn (section 3); a retry waits on the stored hash and never sends a second burn. Every Treasury send goes through `submit_transaction`, which holds `treasury_send_lock`. The burn method is still to be confirmed by a test burn (section 8) | |
| 2026-10-19 | 13, EVM switch-over | R4-08 (#257): one chain-neutral `ChainTxHash` replaces the XRPL-only `TxHash` and `XrplHash` on the transfer, account-history and stuck-settlements pages. `lib/chain.ts` picks the explorer from the hash: `0x…` goes to the XRPL EVM Testnet explorer (`VITE_EVM_EXPLORER_URL`, defaulting to `EVM_EXPLORER_URL`'s value), anything else to testnet.xrpl.org, so older XRPL transfers keep working links and a switch back needs no change (D11). The section 6 code-to-message map is in `lib/stokvel-errors.ts` (#254) | #257 |
| 2026-10-14 | 8, 9 | Burn method confirmed: a 1-base-unit `burn(uint256)` from the Treasury, tx [`0xacfd…9cd6`](https://explorer.testnet.xrplevm.org/tx/0xacfd84b642ff7d30b535bf8256fc572657d54894a444e13039c212d4d68f9cd6) (block 9072949), lowered `totalSupply` from 99999990000000000000000000 to 99999989999999999999999999 base units. The section 8 question is closed | |
| 2026-10-15 | 3, 13, 14 | R2-05 (#227) hardening. The cycle tables' row-level security is now one policy per operation (`SELECT` with the read rule; `INSERT` and `UPDATE` with the write rule) and has no `DELETE` policy: a Postgres probe showed the single `FOR ALL` policy let any member delete cycles, rounds and other members' cycle rows. New trigger `stokvel_cycle_member_same_stokvel` refuses a cycle member from a different stokvel. The group tables (#226) have the same delete gap; a separate ticket is proposed | |
| 2026-10-15 | 8, 9, EVM switch-over | R6-02 (#267), on top of #278: the seeder's `verify --chain` compares the ledger treasury with the Treasury Wallet's UCTUSD balance (`evm_service.get_token_balance(EVM_TREASURY_ADDRESS)`) instead of XRPL trust lines; the seeder isolates the `EVM_TREASURY_*` / `EVM_ENCRYPTION_KEY` settings per target; simulated burn failures read as EVM errors. Load test: `fake_xrpl_worker.py` renamed `fake_evm_worker.py`, `qa_xrpl_timings.sql` renamed `qa_burn_timings.sql` and now measures only EVM burns (hashes starting `0x`), report labels say UCTUSD. Burn timing defaults are still the XRPL figures until QA has real EVM burns | |
| 2026-10-16 | 3, 8, 9, 13, 14 | R2-06 (#228): `stokvel_contributions` built with row-level security. **Changed from the planned UNIQUE (`cycle_id`, `round`, `member_id`)** to a partial unique index over rows that have not failed, so a member can pay again after a failed attempt (otherwise a failed send would block the round for good); needs Roles 2 and 3 approval. Composite foreign keys keep the round and member inside the cycle. Added `created_at` (for limit windows) and `confirmed_at`. New open question: which ledger leg `tx_id` names (R2-11) | |
| 2026-10-16 | 3, 5, 8, 9, 10, 13, 14 | R2-07 (#229): `POST /stokvels` and `GET /stokvels` built (section 5). Creating a stokvel is one transaction: the stokvel, its `STOKVEL` ledger account and the Organiser's membership (their own fiat account in the Stokvel currency, `invitation_id` null). `contribution_amount` is UCTUSD (D13); the ticket comment's "fiat" predates D13. A caller who is not KYC-verified gets 403, one with no account in the Stokvel currency gets 400. The list leaves out stokvels the caller has left and answered invitations, and scopes by user in the query as well as by row-level security. New open questions: where the round schedule is set, list fields that need the cycle and contribution tables, and members inserting their own membership (section 8). Interface change: needs Roles 3 and 4 approval | |
| 2026-10-16 | 3, 5, 6, 8, 9, 13, 14 | R2-11 (#233): `POST /stokvels/{id}/contributions` built. Ledger model agreed with Role 3: contribution = member fiat → bank + Treasury → `STOKVEL` (+ fee leg); pool release = `STOKVEL` → Treasury, so the `STOKVEL` balance equals the unreleased pools in the contract. `stokvel_contributions` gains `fiat_tx_id`, `token_tx_id`, `fee_tx_id` and `amount_zar` (contribution + fee in rand, counted in the member's limits, D8); `tx_id` deprecated. The `transactions` policy now lets members see and record legs on their stokvel's `STOKVEL` account (needs Roles 2 and 3 approval). Stokvel refusals carry a `code` in the error body. Fee rule: next row | |
| 2026-10-16 | Decisions, 3, 5, 6, 8, 11, 14 | Product question 4 answered **A, fee on top** (confirmed by Kerry with product). D6 amended: each member pays an equal share of the round's payout fee (FSE's fixed + percentage fee and, when the recipient is paid in another currency, the FX margin, all on the pool) on top of their contribution, rounded up to the cent; the beneficiary receives the full pool. `contribution_fee_share` implements it and R2-11 records the `fee` leg. The fee-to-fiat question is resolved (the fee is collected in fiat). R3-05 (#242) must not charge the payout's fee again. Sections 5, 6 and 14 now also list the response, the API-only refusals (404, short balance, unverified, over limit), the new error classes, `DomainError.code` and the `get_standing` change | #233 |
| 2026-10-16 | Decisions, 6, 8, 13, 14 | R2-11 review (Claire, #340). The `transactions` change is now two separate policies beside an unchanged `transactions_by_current_user`: `transactions_stokvel_member_select` (read legs on the `STOKVEL` account of a stokvel you are or were a member of) and `transactions_stokvel_member_insert` (record a leg into it while a current member, `stokvel_account_is_active_member`). No update or delete policy, so no member's session can change or remove a stokvel leg. A non-member now gets 404 (as row-level security already gave on Postgres), not 403. Only `uq_stokvel_contributions_once` answers "already paid"; other integrity errors are raised. The fee is priced on the round recipient's locked payout currency. D6 notes the rate drift between shares; R3-05 must not reconcile against it | #340 |
| 2026-10-16 | 5, 6, 8, 9, 11, 14 | R2-11 second review (#340). A contribution looks its rates up before locking the member (`quote_service.token_rates`): a lookup may fetch a live rate and commit, which released the lock. The fiat debit multiplies by the stored USD quote, not a rounded inverse. A lost enqueue is logged loudly, as in `confirm_remittance`. No exchange rate answers 503. `ErrorResponse` in the OpenAPI spec gains an optional `code`. The insert policy now pins both sides: a `stokvel_contribution` leg from the Treasury Wallet (`account_is_treasury_wallet`) into the member's stokvel's account. Section 11 corrected to the agreed release direction (`STOKVEL` → Treasury); R3-03 (#342) and R3-04 to match | #340 |
| 2026-10-17 | 4, 6, 8, 9, 13, 14 | R2-12 (#234): `stokvel.submit_contribution` and `stokvel.confirm_contribution` built in `remitx_worker/stokvel_tasks.py`, over a new contract wrapper `remitx_worker/stokvel_contract.py` (`contribute`, the Treasury allowance check, revert decoding against the vault and `IERC20Errors`). Task names stay `stokvel.<name>` (section 4), the convention for every stokvel task. `confirm_contribution` also takes the receipt's `block_number` (a confirmed row needs it). Platform-side refusals (paused, Treasury short of UCTUSD or allowance, Treasury without `OPERATOR_ROLE`, a failed token transfer) and sends that never reached the chain are retried; contract rule refusals fail the contribution at once. The worker carries a copy of the ABI (its image is built from `api/` only), checked against `contracts/abi/` by a test. Open question added: reclaiming contributions left `pending` or `processing` | #234 |
| 2026-10-18 | none | Comment fix in `V20261016_1500` (from the review of #344): `accounts` has no row-level security, so `account_is_treasury_wallet` is a lookup function for consistency and future-proofing, not because a plain subquery would be hidden. No schema or behaviour change | |
| 2026-10-17 | 3, 5, 6, 8, 9, 10, 13, 14 | R2-08 (#230): `POST /stokvels/{id}/invitations`, `POST /invitations/{id}/accept` and `POST /invitations/{id}/decline` built (section 5). Accepting sets the invitation to `accepted` and inserts the member row in one transaction, under a lock on the `stokvels` row, so `MAX_STOKVEL_MEMBERS` holds for two accepts at once. `stokvel_members` now has one policy per operation and no `DELETE`: a customer may insert their own row only as the Organiser with no invitation, or with their accepted invitation to that stokvel; a trigger fixes `stokvel_id`, `user_id`, `invitation_id` and `joined_at` (section 3; resolves the section 8 question). New lookups `kyc_latest_status` and `stokvel_active_member_count` answer the invitee's KYC for the Organiser and the member count for an invitee, which row-level security hides. New refusal codes (section 6). `GET /stokvels` no longer lists a pending invitation to a deactivated stokvel (#339 review). Interface change: row-level security needs Roles 2 and 3 approval; routes and codes need Roles 2, 3 and 4 (section 5), and Roles 1, 2 and 4 (section 6) | |
| 2026-10-18 | 3, 14 | R2-08 review (#344): `stokvel_member_identity_fixed` also refuses clearing a set `left_at`. Under the own-row `UPDATE` policy a former member's session could set it back to null and be a current member again, with no invitation and past `MAX_STOKVEL_MEMBERS` (reproduced on Postgres; no route did it). Leaving and rejoining makes a new row, as the trigger already said | #344 |
| 2026-10-18 | 3, 8, 14 | R2-08 review (#344, Kerry): `stokvel_invitations` gets one policy per operation and no `DELETE`. Only the Organiser inserts, as inviter and `pending`; the invitee accepts or declines and the Organiser revokes, each recorded as the changer. New trigger `stokvel_invitation_fixed`: an invitation's stokvel, invitee, inviter and creation time are fixed, and an answer is final. Under the old `FOR ALL` policy a customer could forge an accepted invitation to themselves and join any stokvel (reproduced on Postgres). The section 8 member-insert question now covers both tables | #344 |
| 2026-10-18 | 3, 5, 6, 8, 9, 10, 13, 14 | R2-09 (#231): `PUT /stokvels/{id}/payout-order` and `PUT /stokvels/{id}/members/me/beneficiary` built (section 5). No migration: `stokvel_cycle_members` already had the columns. `POST /stokvels` now also opens cycle 1 as `forming` with a row for the Organiser, and accepting an invitation adds the new member's row while the cycle is forming (section 3). This changes R2-07 and R2-08 code, outside the ticket's file list. A stokvel from before this change gets cycle 1 on demand, from its Organiser only: row-level security lets only the Organiser insert a cycle. The beneficiary request carries only `beneficiary_id`; the payout currency is copied from the beneficiary once the recipient is confirmed to still hold that account. New refusal codes `cycle_locked`, `cycle_not_forming`, `invalid_payout_order`; `not_organiser` reused (section 6). Interface change: routes need Roles 2, 3 and 4 (section 5), codes Roles 1, 2 and 4 (section 6) | |
| 2026-10-19 | 6, 8, 14 | R2-09 review (#347, Mridula and Marc): `stokvel_cycle_members.payout_beneficiary_id` references `beneficiaries` with no `ON DELETE`, and `DELETE /beneficiaries/{id}` hard-deletes, so removing a beneficiary a stokvel pays gave a 500. It now answers 409 `beneficiary_in_use_by_stokvel` when any cycle row, of any status, pays it; the member chooses another for that stokvel first. `ON DELETE SET NULL` was ruled out: it breaks `stokvel_cycle_members_locked_is_complete` on a locked row. New section 8 row for R3-05: re-check the copied `payout_currency` at payout. Interface change: the code needs Roles 1, 2 and 4 (section 6) | #347 |
| 2026-10-16 | Proposals, 8 | P6 stays open: the Organiser-set deadline (informational) and the later payout time (hard gate) are both kept, as built. They may be merged into one date later, with no contract change: the backend would send the same date as both (Mridula, #341 review) | |
| 2026-10-16 | 3, 8, 9, 13, 14 | R3-03 (#240): `stokvel_payouts` built with row-level security. Release and remittance have separate statuses, both stored (`release_status`, `remittance_status`), so a retry has a row to claim before any quote exists. The release also stores its ledger leg (`release_tx_id`), block (`release_block_number`) and `released_at`, as a contribution stores `tx_id`, `block_number` and `confirmed_at`. Composite foreign keys tie a payout to its round and to a member of the cycle; trigger `stokvel_payout_member_is_scheduled` refuses a member the round does not pay. Members of the stokvel read; only workers and admin routes write; nobody deletes. The `stokvel_pool_release` leg books `STOKVEL` → Treasury Wallet, as agreed in R2-11 (#340) | #342 |
| 2026-10-19 | 3, 8, 14 | R3-03 review (#342, Marc): new trigger `stokvel_cycle_member_position_is_paid` refuses changing a cycle member's `payout_position` once a payout exists for their round, so the scheduled-member rule holds from both tables (before, the position could move after the payout row was written; reproduced on Postgres). The `remittance_status` CHECK is pinned on purpose rather than built from `TransactionStatus`. The migration now revises `e09d8fb367b5` (R2-08), and the release-direction question in section 8 is closed by R2-11 | #342 |
| 2026-10-18 | 2, 3, 4, 8, 9, 13, 14 | R2-13 (#235): `stokvel.sync_events` built. A beat task reads the vault's `ContributionMade`, `RoundFinalised` and `CycleClosed` logs from a cursor (`stokvel_sync_state`, one row per contract address, worker-only row-level security), range by range, staying `STOKVEL_SYNC_CONFIRMATIONS` behind the head. Each range is one transaction: a compare-and-set on the cursor, then the events, so a crash keeps them together and overlapping runs cannot both apply a range. `ContributionMade` confirms through `stokvel_ledger.record_mined`, the guard `confirm_contribution` now shares; `CycleClosed` closes the cycle; `RoundFinalised` is only noted until R3-04 (#241) builds `release_pool` (proposed interface in section 8). Replaying any range changes nothing. Events for stokvels this database lacks are skipped (the contract is shared). New settings `STOKVEL_SYNC_*` | #235 |
| 2026-10-19 | 4 | R2-13 review (#346, Marc and Mridula): only the cursor's own insert is treated as a race between sync runs; an integrity error from applying an event now fails the run (the cursor stays put) instead of being logged as a race and skipped. A contribution `confirm_contribution` recorded meanwhile is reported as already recorded. Noted: R2-10 must keep `cycle_number` equal to the contract's cycle. Migration `V20261018_1000` now follows #342's payouts table | #346 |
| 2026-10-19 | 2, 3, 4, 13, 14 | R2-13 second review (#346): new `stokvel_held_events`. Each event is applied in its own savepoint; one that fails, will not decode, or disagrees with the database (a different hash) is held as failed for a person, and `RoundFinalised` (until R3-04) and a `CycleClosed` with payouts still unreleased are held as waiting. The cursor moves on, every run retries held events first, so no event stops the sync and none is lost. Decoding moved out of the RPC call (`fetch_logs`, `decode_log`); topics from `eth_utils`. `STOKVEL_SYNC_START_BLOCK` is required once the contract address is set (no scan from genesis). A run that loses a race reports where the cursor is | #346 |
| 2026-10-19 | 5, 9, 10, 14 | R3-12 (#249): audit actions `stokvel.contract.paused`, `stokvel.contract.unpaused`, `stokvel.round.finalised_manually` and subjects `stokvel`, `stokvel_contract` (`STOKVEL_CONTRACT_SUBJECT_ID`). List them with the existing `subject_type` filter. No `stokvel.cancelled` (#208). Pause and manual finalise still call `record_audit` in R3-07 and R3-10 | |
| 2026-10-19 | 3, 4, 5, 6, 8, 9, 13, 14 | R2-10 (#232): `POST /stokvels/{id}/cycles` built (section 5). The round schedule is sent here (resolves the section 8 question). It checks what `startCycle` enforces, plus readiness: every current member has a payout position and a beneficiary, positions exactly `0..n-1`; then, under the stokvels row lock, writes the rounds, lapses pending invitations, locks the current members' rows and makes the cycle `active`. New tasks `stokvel.start_cycle` (`createStokvel` for a new stokvel, then `startCycle`; idempotent from `getStokvel` and the stored hash) and `stokvel.confirm_cycle_start` (section 4). New `stokvel_cycles.start_tx_hash`, `start_block_number`, `registered_at`: contributions answer 409 `cycle_starting` until the cycle is open on-chain. **Changes to others' code:** R2-11 counts only the cycle's locked rows (a former member's unlocked row had made round 0 impossible to fill); `stokvel_invitations_update` lets the Organiser record `lapsed` (R2-08's test updated). New codes `cycle_in_progress`, `too_few_members`, `cycle_not_ready`, `invalid_schedule`, `cycle_starting` (section 6). Interface changes: Roles 2 and 3 (sections 3 and 4), Roles 2, 3 and 4 (section 5), Roles 1, 2 and 4 (section 6) | |
| 2026-10-19 | 2, 4, 5, 8, 14 | R2-10 review (#348, Claire, Kerry and Marc): `stokvel.confirm_cycle_start` is gone: `start_cycle` records the mined start itself, guarded on its stored hash, and retries if that write fails, so a lost second enqueue can no longer strand a mined cycle. Recording a cycle found already open needs no hash stored, so a duplicate cannot record it before the hash owner saves its block. `start_cycle` sends only when the contract is one cycle behind, and records without sending only when this cycle is open there; a contribution that differs or cycle numbers that disagree are left for a person (before, a mismatch was only logged and the cycle started). New beat task `stokvel.register_started_cycles` (setting `STOKVEL_START_SWEEP_INTERVAL_SECONDS`) re-queues unregistered active cycles, so a lost enqueue at the start is picked up and `POST /stokvels/{id}/cycles` answers 201 instead of 500 after its commit. A one-member stokvel's one round now gets 409 `too_few_members`, not 422. The locked-members rule is one query (`locked_members_query`) shared by the API and the worker. Migration `V20261019_1051` now follows #346's `5b1e7c2d9a40`. Interface change: worker tasks need Roles 2 and 3 (section 4) | #348 |
| 2026-10-19 | 9, 13 | R6-01 (#266): new [stokvel_test_plan.md](stokvel_test_plan.md) maps every brief §7.5 test, the §2 demo cases and demo timing to the test that covers it or the ticket and owner that will. Contract tests C1–C9 are covered on `main`. Gaps: the contract tests are not in CI (#262, #289); the stokvel settlement retry test waits on the payout chain (#241 → #242 → #243), and #271 and #243 both plan it; the early-finalisation demo needs #247 | |
**Change rule:** any change to an interface in this file goes through a PR approved by the owners it affects. No one changes an interface quietly inside a feature PR. Every change to this file or to the database model also gets a row at the bottom of [stokvel_changelog.md](stokvel_changelog.md).

---

## Decisions (agreed; change only via PR)

| # | Decision | Source |
|---|---|---|
| D1 | The whole system moves from XRPL to the XRPL **EVM** Testnet. The running system no longer uses the XRPL Testnet, but the XRPL code is kept, not deleted (D11). Lecturer approval received (Marc, 2026-10-07). | Design session, lecturer approval |
| D2 | One custodial EVM **Treasury Wallet** (the existing term is kept). The database ledger, not separate addresses, tells contribution, pool release and burn movements apart. No separate settlement wallet (#207, closed; section 8). | Design session, CONTEXT.md |
| D3 | Users create stokvels and invite other users. The Organiser sets attributes and payout order. **The members agree the payout order among themselves, off the platform.** The platform does not negotiate, vote on or assign it: the Organiser enters the agreed order, and members see it before the cycle starts. The Administrator only has oversight and the global pause. | CONTEXT.md, team 2026-10-14 |
| D4 | One contract deployment holds many stokvels (`mapping(stokvelId => Stokvel)`), each with nested cycles and a per-round pool. History is events plus minimal storage (paid, finalised, entitled member). | Design session |
| D5 | Finalise is automatic. Round N releases once every member has contributed to round N+1 **and round N's payout time has passed** (D12). The last round of a cycle releases once every member has contributed to it and its payout time has passed. | CONTEXT.md, team 2026-10-07 |
| D6 | The Stokvel is the remittance **sender**. The pool is paid to the scheduled member's Payout beneficiary through the existing remittance flow. Fee and margin are **paid by the members on top of their contributions** (product question 4, option A, confirmed 2026-10-16): each member pays an equal share of the round's payout fee and margin, worked out on the pool and rounded up to the cent, so the beneficiary receives the full pool. The payout remittance itself charges no further fee. The margin follows the round recipient's payout currency, which is locked when the cycle starts, so it is the same for every member of the round. **Known prototype gap:** each share is priced at the rate when that member pays, so in a stokvel whose currency is not ZAR, members of one round can pay slightly different shares, and the shares need not add up exactly to the fee on the pool paid out. Nothing refunds or collects the difference; R3-05 must not reconcile the payout's fee against the shares (open question, section 8). | CONTEXT.md |
| D7 | Contributions are paid from the member's fiat account in the Stokvel currency and refunded as the original fiat amount. The deadline is informational only; there are no penalties on the platform. | CONTEXT.md |
| D8 | A Stokvel has no sending limits. Each contribution counts toward the member's own limits. Joining needs the required KYC standing. | CONTEXT.md |
| D9 | The Stokvel gets a ledger `accounts` row of a new type `STOKVEL` (token currency) and is the sender of its payout remittance: the stokvel is the quote's sender (`quotes.stokvel_id`), while the payout's legs start from the Treasury Wallet, as the pool left the `STOKVEL` account at its release. | Team, 2026-10-06 |
| D10 | The "hold the payout until the recipient pays the next round" idea is already covered by D5. The CONTEXT.md rule stays. A per-member early release (release as soon as the recipient alone has paid the next round) is not adopted. | Team, 2026-10-06 |
| D11 | **We switch XRPL off, but we don't delete it.** Only change what the EVM chain needs in order to work, such as the settings it reads, the worker's burn, names and tests. If an XRPL file, script, setting (`XRPL_*`, `PLATFORM_WALLET_*`, `UCTUSD_ISSUER*`) or the `xrpl-py` package can stay without stopping EVM from working, leave it where it is and add a comment saying it is no longer used. The running system never calls it. This way we can go back to XRPL later without starting from scratch. | Team, 2026-10-06 (settings); extended to code, 2026-10-14 |
| D12 | Each round has a **payout time**, set by the Organiser. It is a hard gate: `finalise` reverts before it (brief §7.1). If the payout time passes while a member has not paid, the round stays blocked, not lost, and releases once the last member pays. The contribution **deadline** stays informational (D7). A contract cannot run itself on a date, so a scheduled backend task calls `finalise` for rounds that are due (section 4); the final `contribute` call still triggers the release when the time has already passed. | Team, 2026-10-07 |
| D13 | Contribution amount is a fixed **UCTUSD** (token) amount for the stokvel's life, set in `createStokvel` and stored as `stokvels.contribution_amount`. Member fiat debit = token amount × live rate at contribution. A new amount means a new stokvel (MVP). | Product, 2026-10-11 |

## Proposals for product (status: Proposed)

These come from the dev team and need product approval before they are treated as requirements.

| # | Proposal | Why | Status |
|---|---|---|---|
| P1 | **Users create stokvels and invite other users**, instead of a RemitX admin creating them (brief §2 step 1). | Scales better and removes the admin bottleneck. The admin keeps oversight only. | Proposed |
| P2 | **Payout hold to reduce defaulting after payout.** The contract holds a round's pool until the next round is fully paid **and the round's Organiser-set payout time has passed** (D12), so a member who has already been paid cannot stop contributing without blocking everyone. The final round has no next round, so it pays out once everyone has paid it and its payout time has passed. | Mitigates the default risk the brief names. It is the same rule as D5. | Proposed, needs legal review |
| P3 | **Member cap of 3 for the prototype, built to grow.** One constant sets the limit: backend `MAX_STOKVEL_MEMBERS`, and a `maxMembers` value in the contract set at deployment. No fixed-size arrays; round counts are `uint8` (up to 255); cycle length equals the number of members. Raising the limit to 10 or 12 (#197) is a config change. | Brief says three members. Building for more costs little now. | Proposed |
| P4 | **Cancellation.** Ending a stokvel, including partway through a cycle, stops future rounds and refunds unfinalised contributions in the original fiat. Possibly admin-only, on request. | Reverses the brief's "refunds out of scope". | **Not in v1** (product, 2026-10-09): cancellation, refunds and disputes are out of scope (#208) |
| P5 | **Manual admin finalise as a fallback.** Finalisation stays automatic (D5), but the Administrator can also trigger it for a round if the automatic release fails. The contract still enforces the release conditions, so a call on a round that is not ready is rejected (`NotYetFinalisable`). Also gives the demo a natural way to show a blocked finalisation. | Restores the brief's admin finalise (§7.3) as a safety net. Covers a failed trigger only, not a paused contract or RPC outage. | **Approved** (product, Sian, 2026-10-19: keep an admin Release payout button as a fallback) |
| P6 | **Merge the contribution deadline and the payout time into one date per round.** The build keeps both: the Organiser sets a deadline members are expected to pay by (informational, D7) and a later payout time (a hard gate, D12). Merging them needs no contract interface change or redeploy: the contract keeps both fields and the backend sends the same date as both (Mridula, #341 review). | One date is simpler for Organisers and members. | Question for product. Both kept for now, as built (2026-10-16) |

**Legal questions for product (P2):** is a payout that is conditional on a later contribution permitted under South African consumer-protection law and the stokvel exemption from the Banks Act? Trade-off to note: one late payer delays everyone's payout, because every member must have paid before a round releases.

**Stuck rounds (D12, P2):** if a member never pays, the round stays blocked for everyone indefinitely. There are no penalties (D7), so the only way out is cancellation and refunds (P4). Product should see this trade-off, which makes P4 more important.

## Deviations from the brief

The brief (§2, §7, §9) describes one stokvel, three members, an administrator who sets it up and finalises each round, and lists multiple stokvels and refunds as out of scope. This build extends it:

- Many stokvels in one contract, multiple cycles, user-created with invitations (D3, D4, P1).
- A round releases only when fully paid **and** its Organiser-set payout time has passed (D12), matching brief §7.1. The contribution deadline stays informational.
- Finalisation is automatic (D5), with a manual Administrator finalise as a fallback (P5); the brief has the administrator do it every round. A round that becomes due with time rather than with a payment is released by the scheduled release (R3-11, #248) within `STOKVEL_RELEASE_INTERVAL_SECONDS` of its payout time; the Administrator's finalise stays as the fallback.
- Cancellation and refunds (P4) are not in v1 (section 8), so the brief's "refunds out of scope" still holds.
- TrustMeBank deposits and withdrawals (#202, #203), optional in the brief, are built as required.
- The XRP Ledger is replaced by the EVM chain (D1).
- A payout's remittance keeps the existing ledger states (`pending`, `processing`, `confirmed`, `failed`) rather than the brief's `created → burning → burnt → credited` (section 8).

The final demo must still show everything the brief requires: three synthetic members across three rounds, a round blocked because one member has not paid, and a duplicate contribution and an early finalisation being rejected. If the contract is not deployed and tested by Friday 9 October, reduce scope (drop cancellation and multi-cycle first, then TrustMeBank deposits and withdrawals, #202 and #203, last), as the brief instructs.

---

## 1. Contract interface (Role 1)

> Confirmed by Role 1 against the contract on `main` (`contracts/src/StokvelVault.sol`, merged in #282), including the error-order fix from #291 (merged 2026-10-09), **with one open item**: the ID scheme (packed UUID vs a separate generated `bytes32`) is still under discussion (section 8). Cancel and refund are not built yet (R1-06, #220, waiting on #208); they are listed as planned.

### Units and IDs

- Amounts are in UCTUSD's smallest unit (18 decimals).
- Stokvel and member IDs are database UUIDs packed into `bytes32`, left-aligned (the 16 UUID bytes first, the rest zero). Example: `5f0c2a1e-8d3b-4c6a-9e71-2b4f6d8a0c13` → `0x5f0c2a1e8d3b4c6a9e712b4f6d8a0c1300000000000000000000000000000000`. The reference helper is `uuidToBytes32` in `contracts/test/helpers.ts`; the backend helper must produce the same bytes. **Open (section 8):** whether to pack the UUID like this or give each stokvel and member a separate generated `bytes32` ID. The contract accepts any non-zero `bytes32` either way; this is a backend decision.
- **Member IDs are per-stokvel row UUIDs** (`stokvel_members.id`), not user IDs. Everything on-chain is public and permanent; a user ID would link one person's stokvels.
- Limits: minimum members 2 (constant `MIN_MEMBERS`). Maximum is `maxMembers`, a constructor argument (3 for the prototype; see P3).
- Contribution amount is a fixed UCTUSD amount set by `createStokvel` and used for every cycle of that stokvel. **MVP decision (2026-10-09):** the amount cannot change between cycles; to use a different amount, the Organiser creates a new stokvel (the old one stays on-chain, inactive, with its history). Per-cycle amounts are a possible later change (move the amount into `startCycle`), not in the MVP.

### Deployment

`constructor(address admin, address operator, IERC20 token, address releaseTarget, uint8 maxMembers)`

| Argument | Value (section 2) | Notes |
|---|---|---|
| `admin` | Deployer | Gets `DEFAULT_ADMIN_ROLE`. Must differ from `operator` (`AdminIsOperator`) |
| `operator` | Treasury Wallet | Gets `OPERATOR_ROLE` |
| `token` | UCTUSD | |
| `releaseTarget` | Treasury Wallet | Where released pools go (D2). A separate argument so #207 can change it without a code change |
| `maxMembers` | 3 | At least 2 (`InvalidMaxMembers`) |

### Roles (OpenZeppelin AccessControl)

| Role | Held by | Can |
|---|---|---|
| `DEFAULT_ADMIN_ROLE` | Platform owner (deployer) | Grant roles, pause and resume |
| `OPERATOR_ROLE` | Backend, via the Treasury Wallet | Create stokvels, start cycles, submit contributions, finalise (and refund, when built) |

The contract relies on the backend to identify the contributing member (brief §7.4); this is documented in the contract's NatSpec and will go in the contract README (R1-05).

### Functions

| Signature | Caller | Purpose |
|---|---|---|
| `createStokvel(bytes32 id, uint256 contribution)` | Operator | Register a stokvel and its fixed contribution. Emits `StokvelCreated` |
| `startCycle(bytes32 id, bytes32[] memberIds, uint64[] roundStartTimes, uint64[] roundDeadlines, uint64[] payoutTimes)` | Operator | Start the next cycle: fix members (payout order = array order; round *i* pays `memberIds[i]`) and the schedule. One round per member. Only when no cycle is open (the first, or after the previous one closed). `roundStartTimes` and `roundDeadlines` are informational; `payoutTimes` is enforced (D12). Each round needs start ≤ deadline ≤ payout, and start and payout times may not go backwards from one round to the next (equal is allowed). Emits `CycleStarted` |
| `contribute(bytes32 id, uint8 round, bytes32 memberId)` | Operator | Pull exactly `contribution` UCTUSD from the Treasury Wallet and record it against member and round. Rounds fill in order: a round accepts contributions only once every earlier round is fully paid. Late contributions are accepted (deadline informational). Releases any round that has become due. Emits `ContributionMade` (and `RoundFinalised` / `CycleClosed`) |
| `finalise(bytes32 id, uint8 round)` | Operator | Release one round's pool to the release target (Treasury Wallet) and record the entitled member. `round` must be the next round to release. Reverts `NotYetFinalisable` unless the paid condition (D5) holds **and** `block.timestamp >= payoutTimes[round]` (D12). Emits `RoundFinalised` (and `CycleClosed` after the last round) |
| `pause()` / `unpause()` | Admin | Halt or resume `contribute` and `finalise` (and `refund`, when built) for every stokvel; never bypasses conditions. `createStokvel`, `startCycle` and views keep working |
| `cancel(bytes32 id)` | Operator (admin-requested) | **Planned (R1-06, #220).** Stop the stokvel; mark contributions to unfinalised rounds refundable |
| `refund(bytes32 id, uint8 round, bytes32 memberId)` | Operator | **Planned (R1-06, #220).** Return one refundable contribution to the Treasury Wallet |

**Automatic finalisation (D5, D12):** when a `contribute` call completes round N+1 (or completes the last round) and round N's payout time has already passed, the same transaction releases round N. If everyone paid before the payout time, nothing happens on-chain until the time passes: the backend's scheduled release task (section 4) polls `isFinalisable` and calls `finalise`, once per due round. One `contribute` releases every round that is due, so it can release several rounds at once: a round that became due with time but was not yet finalised, together with the round the contribution makes due. The final contribution of a cycle, made after the last payout time, always releases at least the second-last and the last. No person needs to trigger a release; the Administrator can as a fallback (P5), through the backend's operator key.

Uses OpenZeppelin `AccessControl`, `Pausable`, `ReentrancyGuard` and `SafeERC20`. State is updated before every token transfer, and `contribute` and `finalise` are `nonReentrant`.

### Treasury allowance (agreed with the backend, 2026-10-08)

`contribute` pulls the contribution with `safeTransferFrom(msg.sender, vault, contribution)`, so the Treasury Wallet must have approved the vault for UCTUSD first.

- **One-off approval at setup:** the Treasury calls `UCTUSD.approve(STOKVEL_CONTRACT_ADDRESS, type(uint256).max)` once per contract address.
- **Check before each `contribute`:** the worker reads `UCTUSD.allowance(treasury, vault)` and re-approves if it is below the contribution. This also covers a redeploy, because a new contract address needs a new approval.
- **Why not one approval per contribution:** the vault only ever pulls from `msg.sender`, and only `OPERATOR_ROLE` (the Treasury) can call `contribute`, so the allowance can only be spent by Treasury-signed calls. Per-contribution approvals would double the transactions and add nonce ordering without adding protection.
- **Re-approving is safe on UCTUSD:** checked on the testnet (2026-10-09, simulated `eth_call`) that `approve` from a non-zero allowance to a new non-zero amount succeeds. There is no USDT-style "set to zero first" rule. UCTUSD behaves like an OpenZeppelin ERC20.
- **A missing or short allowance** reverts with the token's `ERC20InsufficientAllowance` (from UCTUSD, not the vault). It is a backend fault, not a user error (section 6).
- **Token errors are not in the vault's ABI.** `ERC20InsufficientAllowance(address spender, uint256 allowance, uint256 needed)` (selector `0xfb8f41b2`) and `ERC20InsufficientBalance(address sender, uint256 balance, uint256 needed)` (selector `0xe450d38c`) are raised by UCTUSD during `contribute`'s pull, so `contracts/abi/StokvelVault.json` cannot decode them. Decode revert data against both the vault ABI and OpenZeppelin's ERC20 errors (`IERC20Errors`); the backend does this (confirmed by Role 2, 2026-10-09).

### Custom errors

| Error | Raised when |
|---|---|
| `NotMember(bytes32 memberId)` | The member ID is not in the stokvel's current cycle |
| `AlreadyPaid(uint8 round, bytes32 memberId)` | The member has already contributed to that round, including one that has since filled or been released. `contribute` checks member, then already paid, then round (#291), so a repeat payment always reports `AlreadyPaid` and a non-member always gets `NotMember` |
| `WrongRound(uint8 round, uint8 openRound)` | The round is not the one currently open for contributions, or does not exist. `openRound` equals the member count once every round is paid, and then every round is rejected (#291) |
| `WrongAmount(uint256 expected, uint256 received)` | The vault received a different amount from the contribution (it measures its own balance before and after the pull) |
| `NotYetFinalisable(uint8 round)` | Release conditions are not met: not the next round to release, not all members paid the next round, the last round is not fully paid, or the round's payout time has not passed |
| `AlreadyFinalised(uint8 round)` | The round was already released |
| `CycleNotOpen(bytes32 id)` | No cycle has started, or the current cycle has closed (or, when built, the stokvel was cancelled). Named `CycleClosed` in earlier drafts; renamed because Solidity does not allow an error and an event (`CycleClosed`) to share a name |
| `UnknownStokvel(bytes32 id)` | The stokvel ID is not registered |
| `MaxMembersExceeded(uint256 count, uint8 maxMembers)` | `startCycle` is given more members than `maxMembers` |

Input validation (operator or deployment mistakes, not user errors): `ZeroId`, `StokvelExists(id)`, `ZeroContribution`, `CycleInProgress(id)` (`startCycle` while a cycle is open), `TooFewMembers(count)`, `ZeroMemberId`, `DuplicateMember(memberId)`, `ScheduleLengthMismatch`, `InvalidSchedule(round)`, `UnknownCycle(cycle)` (`getCycle`), `InvalidMaxMembers`, `ZeroAddress`, `AdminIsOperator`.

Access and pause failures use OpenZeppelin's own errors (`AccessControlUnauthorizedAccount`, `EnforcedPause`).

### Events

| Event | Indexed | Other fields |
|---|---|---|
| `StokvelCreated(bytes32 indexed id, uint256 contribution)` | `id` | `contribution` |
| `CycleStarted(bytes32 indexed id, uint32 cycle)` | `id` | `cycle` (1 for the first cycle) |
| `ContributionMade(bytes32 indexed id, uint32 cycle, uint8 round, bytes32 indexed memberId, uint256 amount)` | `id`, `memberId` | `cycle`, `round`, `amount` |
| `RoundFinalised(bytes32 indexed id, uint32 cycle, uint8 round, bytes32 indexed memberId, uint256 pool)` | `id`, `memberId` | `cycle`, `round`, `pool`. `memberId` is the entitled member (`memberIds[round]`) |
| `CycleClosed(bytes32 indexed id, uint32 cycle)` | `id` | `cycle` |
| `Paused(address account)` / `Unpaused(address account)` | none | OpenZeppelin; `account` is the admin who acted |
| `StokvelCancelled(bytes32 indexed id)` | `id` | **Planned (R1-06)** |
| `ContributionRefunded(bytes32 indexed id, uint8 round, bytes32 indexed memberId, uint256 amount)` | `id`, `memberId` | **Planned (R1-06)** |

`cycle` is in `ContributionMade` and `RoundFinalised` (added to the earlier draft) so the event sync can tell cycles apart. Events are the history. The contract's storage holds only what the rules need: per-round paid flags, paid counts and pools, the next round to release, the members and schedule per cycle, and the current cycle.

### View functions

All views except `getCycle` read the stokvel's **current (latest) cycle**. Each reverts `UnknownStokvel` for an unregistered ID.

| Signature | Returns |
|---|---|
| `getStokvel(bytes32 id)` | `(uint256 contribution, uint32 currentCycle, bool cycleOpen)`. `currentCycle` is 0 before the first cycle |
| `getCycle(bytes32 id, uint32 cycle)` | `(bytes32[] members, uint64[] roundStartTimes, uint64[] roundDeadlines, uint64[] payoutTimes, uint8 nextToFinalise, bool closed)`. Rounds below `nextToFinalise` are released. Reverts `UnknownCycle` for 0 or a cycle not yet started |
| `hasPaid(bytes32 id, uint8 round, bytes32 memberId)` | `bool` |
| `roundPool(bytes32 id, uint8 round)` | `uint256` tokens held for the round (0 once released) |
| `isFinalisable(bytes32 id, uint8 round)` | `bool`: whether `finalise(id, round)` would succeed now. Ignores pause (check `paused()` separately). `false` when no cycle is open |
| `isMember(bytes32 id, bytes32 memberId)` | `bool` |
| `paidCount(bytes32 id, uint8 round)` | `uint8` members who have paid the round |
| `openRound(bytes32 id)` | `uint8` the round open for contributions. Reverts `CycleNotOpen` if no cycle is open |
| `paused()` | `bool` (OpenZeppelin) |
| `maxMembers()`, `token()`, `releaseTarget()`, `MIN_MEMBERS()` | Deployment settings |

---

## 2. Network and addresses

| Item | Value |
|---|---|
| Network | XRPL EVM Testnet |
| Chain ID | 1449000 |
| RPC URL | `https://rpc.testnet.xrplevm.org` |
| UCTUSD address | `0x7055071C7B79A859d9514e62833BFf041ce71074` (18 decimals) |
| UCTUSD distributor | `0xE054D006c45586251872a7EA17Af40b907745293` |
| Stokvel contract address | `0x2f240705314BB79780522635eA47d20072CB8Fe1` (`StokvelVault`, deployed 2026-10-09, block 8995825; `maxMembers` 3). Source verified on Sourcify (exact match): https://repo.sourcify.dev/1449000/0x2f240705314BB79780522635eA47d20072CB8Fe1. Explorer: https://explorer.testnet.xrplevm.org/address/0x2f240705314BB79780522635eA47d20072CB8Fe1 |

The sidechain has no trust lines; a wallet address is enough to hold UCTUSD. Test XRP pays gas (faucet: XRPL EVM Testnet). 

### Wallet roles (addresses only, never keys)

| Role | Address |
|---|---|
| Deployer (contract admin) | `0x4948b5bf3C39d63a24918de9B0346B6159f7829C` (key in Kerry's local `.env` only; funding in #224) |
| Treasury Wallet (also the contract's operator and release recipient, per D2) | `0x6C350A0A9031DE51dF0535e2e88872Cd7330F2e7` (funded per #224) |

### Environment variables

Added to `.env.example` (and `.env.minimal.example` if local dev needs them). They supersede `XRPL_TESTNET_URL`, `XRPL_ENCRYPTION_KEY`, `PLATFORM_WALLET_ADDRESS`, `PLATFORM_WALLET_SEED_ENCRYPTED`, `UCTUSD_ISSUER` and `UCTUSD_ISSUER_LABEL`.

**The XRPL variables are decommissioned, not removed.** Leave them in `.env` and `.env.example` (and in `config.py`), marked as decommissioned with a comment, and make sure no EVM code path reads them. Do not delete them as part of the EVM switch-over.

| Name | Meaning |
|---|---|
| `EVM_RPC_URL` | RPC endpoint |
| `EVM_CHAIN_ID` | 1449000 |
| `UCTUSD_CONTRACT_ADDRESS` | The ERC-20 token |
| `STOKVEL_CONTRACT_ADDRESS` | The stokvel contract |
| `STOKVEL_SYNC_START_BLOCK` | Event sync (#235): first block for a contract with no cursor, its deployment block (8995825). **Required wherever `STOKVEL_CONTRACT_ADDRESS` is set:** with no cursor and no start block the sync refuses to run (`event=stokvel.sync_misconfigured`) rather than scan from genesis. GCP sets this with the contract address and `MAX_STOKVEL_MEMBERS` on the API and the worker (`infra/gcp/locals_env.tf`), defaulting to `contracts/deployments/xrplEvmTestnet.json`. A `TF_VAR_*` GitHub variable overrides; an empty value omits it |
| `EVM_STOKVEL_ADMIN_ADDRESS`, `EVM_STOKVEL_ADMIN_KEY_ENCRYPTED` | Vault admin, pause and unpause only. Worker only. The key is a Secret Manager secret, Fernet-encrypted with `EVM_ENCRYPTION_KEY`. No default: unset means pause cannot sign |
| `STOKVEL_SYNC_CONFIRMATIONS`, `STOKVEL_SYNC_BLOCK_RANGE`, `STOKVEL_SYNC_MAX_RANGES`, `STOKVEL_SYNC_INTERVAL_SECONDS` | Event sync: blocks behind the head (2), blocks per `eth_getLogs` (2000), ranges per run (10), beat interval (30 s) |
| `STOKVEL_START_SWEEP_INTERVAL_SECONDS` | How often `stokvel.register_started_cycles` runs, and how old an unregistered started cycle must be before it is re-queued (300 s) |
| `STOKVEL_RELEASE_INTERVAL_SECONDS` | How often `stokvel.release_due_rounds` runs (60 s), so a round paid before its payout time goes out within about this long of it |
| `STOKVEL_RELEASE_STUCK_LOG_SECONDS` | How long a payout may sit `processing` with no hash before `stokvel.release_due_rounds` logs it `stokvel.release_sweep_stuck` (600 s). Separate from the interval, as `SETTLEMENT_PROCESSING_STALE_LOG_SECONDS` is for settlement, so a `release_pool` waiting on the Treasury send lock or an RPC retry is not reported |
| `EVM_TREASURY_ADDRESS` | The Treasury Wallet address |
| `EVM_TREASURY_KEY_ENCRYPTED` | Encrypted Treasury Wallet private key; decryption key held outside the database |
| `EVM_ENCRYPTION_KEY` | Fernet key that decrypts it (as `XRPL_ENCRYPTION_KEY` does today) |
| `MAX_STOKVEL_MEMBERS` | Member cap (3 for the prototype; see P3). Must equal the contract's `maxMembers` |
| `DEPLOYER_PRIVATE_KEY` | **The value lives only in the deployer's `contracts/.env`** (gitignored), not the repo-root `.env`, because docker compose loads the root `.env` into the API and worker containers. Never committed, never on Render. `.env.example` lists it only as a commented-out, empty placeholder (#284). Read only by `contracts/scripts/deploy.ts`; the deployer becomes the contract admin |

The contract deploy script (`npm run deploy:testnet` in `contracts/`; PR #284) reads `EVM_RPC_URL`, `EVM_CHAIN_ID`, `UCTUSD_CONTRACT_ADDRESS`, `EVM_TREASURY_ADDRESS` and `MAX_STOKVEL_MEMBERS` from the repo-root `.env` (section 2's values are the defaults for the public ones), and `DEPLOYER_PRIVATE_KEY` from `contracts/.env`. A blank value counts as unset and falls back to the default. The script records the address in `contracts/deployments/<network>.json` as soon as the contract exists, before its post-deploy checks, and adds the check result (`postDeployChecks`), so a failed check never loses the address. `FORCE_REDEPLOY=1` (one-off) replaces an existing record.

Keys never appear in the frontend, API responses, logs or git.

---

## 3. Database model (Roles 2 and 3)

Moved to [stokvel_database_model.md](stokvel_database_model.md): tables, row-level security, ledger changes, status values and transitions, where on-chain values are stored, and idempotency rules.

---

## 4. Worker tasks (Roles 2 and 3)

Celery tasks, queued by name over the broker (the API never imports `remitx_worker`). As in the existing settlement path, the task that makes the network call is separate from the task that records the result in the database, so the database step can be retried on its own.

| Task | Payload | Queued by | Retry behaviour |
|---|---|---|---|
| `stokvel.submit_contribution` | `contribution_id` | API on `POST /stokvels/{id}/contributions` | **Built (R2-12, #234).** Guarded claim `pending → processing` (with its legs); a redelivery waits on the stored hash or does nothing, so it never sends twice. Checks the Treasury's allowance for the vault first and approves `type(uint256).max` if short (section 1). The hash is stored after signing and before the send. A call whose gas estimate reverts is never sent: a rule refusal (`NotMember`, `AlreadyPaid`, `WrongRound`, `CycleNotOpen`, `UnknownStokvel`, `WrongAmount`) fails it; a platform refusal (`EnforcedPause`, `ERC20InsufficientBalance`, `ERC20InsufficientAllowance`, `AccessControlUnauthorizedAccount`, `SafeERC20FailedOperation`) or an RPC error before the send hands the claim back and retries (60 s apart, 10 times), then fails it. A send the RPC refused leaves no hash behind, even once it fails, so the member's retry can sign the same transaction. A hash that may have reached the chain is only ever waited on: no receipt after the retries leaves it `processing` for a person (`event=stokvel.contribution_unconfirmed`) |
| `stokvel.confirm_contribution` | `contribution_id`, `tx_hash`, `block_number`, `error` | `submit_contribution` | **Built (R2-12, #234).** DB-only; guarded on the contribution being `pending` or `processing`, so a replay changes nothing. With a hash and block: the contribution and its legs become `confirmed` and the legs move their balances in one commit. Without: the contribution and its legs become `failed`, which frees the member's held balance and reopens their place in the round; no balance changes |
| `stokvel.start_cycle` | `cycle_id` | API on `POST /stokvels/{id}/cycles`, after the commit; `stokvel.register_started_cycles` | **Built (R2-10, #232).** Reads `getStokvel` first: not registered → `createStokvel(id, contribution_amount)` (cycle 1 only), waited on, and a `StokvelExists` refusal or a reverted duplicate is fine once `getStokvel` finds it; this cycle open on-chain (`currentCycle == cycle_number` and `cycleOpen`, an earlier delivery's hash lost) → nothing is sent and it is recorded, only while no hash is stored. The contract one cycle behind (`currentCycle == cycle_number - 1`) → sends `startCycle` with the locked members in payout order and the rounds' Unix seconds, storing the hash after signing and before the send, guarded on none being stored, so only one delivery sends and a redelivery waits on the stored hash. Anything else (a contribution that differs, cycle numbers that disagree, this cycle closed on-chain, a later cycle of a stokvel the contract lacks) sends nothing and is left for a person (`event=stokvel.cycle_start_needs_person`). Once mined, the task itself sets `registered_at` and the block, guarded on the stored hash, after which the API takes contributions; a database error there retries the task. `AccessControlUnauthorizedAccount` (no `OPERATOR_ROLE`), an RPC error before signing, or a send the RPC refused (its hash cleared) is retried, 60 s apart, 10 times; any other refusal, a reverted `startCycle` or no receipt after the retries is left for a person (`event=stokvel.cycle_start_refused`, `cycle_start_reverted`, `cycle_start_unconfirmed`), and contributions wait |
| `stokvel.register_started_cycles` | none (beat) | Celery beat, every `STOKVEL_START_SWEEP_INTERVAL_SECONDS` | **Built (R2-10, #232 review).** Queues `stokvel.start_cycle` for every `active` cycle with no `registered_at` that started at least one interval ago: a start whose enqueue was lost, or a task that gave up. Safe to repeat (see above); a cycle left for a person is tried, and logged, again each run until it is fixed (`event=stokvel.cycle_sweep`) |
| `stokvel.release_pool` | `cycle_id`, `round` | **Built (R3-04, #241).** The scheduled release (R3-11, #248) and the Administrator fallback (R3-10, #247), through `queue_service.enqueue_release_pool`, for a round due with time rather than with a contribution. Never the event sync, which records releases itself | Creates the payout row if missing and claims it `pending → processing`; stores the hash before sending `finalise`, so a redelivery waits on it. `AlreadyFinalised` (a `contribute` released it; the sync records it) and `NotYetFinalisable` send nothing and hand the claim back; a pause or RPC error retries (60 s, 10 times). On the receipt, records through `stokvel_ledger.record_pool_release`; if that cannot yet (a contribution in the pool unrecorded), the sync records it from the event. A reverted `finalise` hands the claim back only if the payout still holds its hash. No receipt after the retries leaves it `processing` for a person |
| `stokvel.settle_payout` | `payout_id` | **Built (R3-05, #242).** The event sync, at the end of every run and after its commits, through `stokvel_payouts.queue_released_payouts` → `queue_service.enqueue_settle_payout`: every payout `released` with `remittance_status` `pending` and no quote, at most 50 a run. Queued once as soon as it is released, then again only `REQUEUE_AFTER` (5 minutes) after it was last queued (`settle_queued_at` marks it, so another write to the row does not delay it), longest waiting first, so a busy worker is not sent copies and a few failing payouts cannot keep the rest out. So a release recorded by the sync or by `release_pool` is paid out within one sync interval, and a lost message is queued again | No Celery retries; the next sync run queues it again. Skips a payout not `released` or already started. Checks the member's Payout beneficiary: it still exists, still pays out in the member's `payout_currency`, and its user holds UCTUSD and payout-currency accounts; if not, the payout becomes `failed` with nothing created, for a person (`event=stokvel.payout_needs_a_person`, with a fixed reason code such as `beneficiary_payout_currency_changed`, so no beneficiary or recipient ids are logged). So does a missing platform account the legs need (the payout-currency bank, the Treasury or the token issuer): a deployment fault no retry fixes. Prices with `quote_service.price_stokvel_payout` in its own session, before any lock; an unavailable rate leaves it `pending`. Then, in one commit: the `USED` quote, the four pending legs (section 3), the remittance, and the guarded `pending → processing` update with `quote_id` and `remittance_id`. A delivery whose update matches nothing rolls everything back (`already_started`). **Built (R3-06, #243):** after that commit it queues `settle_remittance(quote_id)`, handing the remittance to the existing burn chain, which finishes the payout `confirmed` or `failed` (section 3). If that enqueue fails it is logged (`event=stokvel.payout_hand_off_failed`) and not raised: the legs are all pending, so the reclaim sweep (`reclaim_stuck_settlements`, `SETTLEMENT_RECLAIM_MIN_AGE_SECONDS`) queues it |
| `stokvel.release_due_rounds` | none (beat) | Celery beat, every `STOKVEL_RELEASE_INTERVAL_SECONDS` (60 s) | **Built (R3-11, #248).** For each `active` cycle with `registered_at` set, takes the next round with no `released` payout and keeps it if its `payout_time` has passed, every member's contribution is `confirmed` for it and for the round after (unless it is the last; D5), and its payout is missing or `pending`. Confirms each with the contract's `isFinalisable`, then queues `stokvel.release_pool(cycle_id, round)` (`queue_service.enqueue_release_pool`). One round per cycle per run, since rounds release in order. Queues nothing while the contract is `paused()`. A payout `processing` with no hash for longer than `STOKVEL_RELEASE_STUCK_LOG_SECONDS` (600 s) is logged `stokvel.release_sweep_stuck` and left for a person. A failed read or enqueue is logged and tried on the next run. Idempotent: the claim guard and the contract's `AlreadyFinalised` stop a double release (D12) |
| `stokvel.sync_events` | none (beat) | Celery beat, every `STOKVEL_SYNC_INTERVAL_SECONDS` | **Built (R2-13, #235).** First retries the held events (`stokvel_held_events`), oldest first. Then reads the vault's logs from the cursor in ranges of `STOKVEL_SYNC_BLOCK_RANGE` (at most `STOKVEL_SYNC_MAX_RANGES` per run), staying `STOKVEL_SYNC_CONFIRMATIONS` behind the head. Each range is one transaction: compare-and-set the cursor (only from the block this run read; on Postgres an overlapping run waits, then matches nothing and stops, reporting where the cursor now is), then each event in chain order **in its own savepoint**. An event that waits for something not built yet, raises, will not decode, or disagrees with the database is held instead, so the cursor moves on: no single event can stop the sync, and none is lost. An RPC error leaves the cursor for the next run. Every handler is guarded, so a replayed range changes nothing. Events are matched to `stokvel_cycles.cycle_number`, so **R2-10 (#232) must keep `cycle_number` equal to the contract's cycle** (1 for the first `startCycle`) |
| `stokvel.refund` | `contribution_id` | Cancellation | Claim guard; refund original fiat to the source account |

All stokvel tasks are registered as `stokvel.<name>` in `api/remitx_worker/stokvel_tasks.py` (`stokvel.release_pool` and `stokvel.release_due_rounds` in `stokvel_release.py`, `stokvel.settle_payout` in `stokvel_payouts.py`) (agreed for R2-10, #232, too); the settlement tasks keep `remitx_worker.tasks.<name>`. The contract calls go through `api/remitx_worker/stokvel_contract.py`.

### Contract event → database update

| Event | Effect |
|---|---|
| `ContributionMade` | **Built (#235).** Mark the contribution `confirmed` with the event's hash and block, and move its legs' balances, through `stokvel_ledger.record_mined` (the same guard as `confirm_contribution`, so it is credited once whichever sees it first). Already confirmed: no change. Held as failed, for a person, with nothing changed: the stored hash differs from the event's, or the database has it failed or not at all |
| `RoundFinalised` | **Built (#241).** `stokvel_sync._round_finalised` records the release inline through `stokvel_ledger.record_pool_release`, the guard `release_pool` shares: the payout row (created if missing) becomes `released` with the event's hash and block, and the pool is booked `STOKVEL` → Treasury once. Already released with this hash: no change. A member the round does not pay, or another hash: held as failed, nothing changed. A pool whose contributions are not all recorded yet (`STOKVEL` would go below zero): held and retried on the next run. Events held as waiting before #241 are replayed by the next run |
| `CycleClosed` | **Built (#235).** Close the cycle (`active → closed`, `closed_at`) only once every round's payout is `released`; until then held as waiting. The last round's `RoundFinalised` comes in the same transaction, so this keeps a cycle from closing with a payout unrecorded and a new cycle from opening early. Already closed: no change. **R2-15 (#237):** the same transaction opens the next cycle as `forming` (`open_next_cycle`, under the `stokvels` row lock, so a member accepting meanwhile is not missed): a row for the Organiser with their beneficiary (their closed row's `continued` set true), and an empty row for each current member who was not in the closed cycle. Nothing for a deactivated stokvel or one with a cycle already open. Everyone else in the closed cycle chooses (section 5) |
| `StokvelCancelled` / `ContributionRefunded` | Mark the stokvel `cancelled`; queue refunds |

---

## 5. REST API (Roles 2, 3 and 4)

> Write first (week-1 deadline). Once routes exist, `frontend/openapi.json` is the source of truth for exact fields; this section only agrees shapes beforehand. Each route needs a `summary=`, `responses=error_responses(...)` and a dotted `Tag` (`stokvels`, `admin.stokvels`); run `python scripts/export_openapi.py` afterwards.

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /stokvels` | Authenticated user (KYC standing) | Create a stokvel |
| `GET /stokvels` | Authenticated user | List the caller's stokvels and pending invitations |
| `POST /stokvels/{id}/invitations` | Organiser | Invite a user. **Built (R2-08, #230)** |
| `POST /invitations/{id}/accept` | Invitee | Accept an invitation. **Built (R2-08, #230)** |
| `POST /invitations/{id}/decline` | Invitee | Decline an invitation. **Built (R2-08, #230)** |
| `POST /invitations/{id}/revoke` | Organiser | Revoke a pending invitation. **Built (R2-16, #297)** |
| `PUT /stokvels/{id}/payout-order` | Organiser | Enter the payout order the members agreed off the platform (D3), before a cycle. **Built (R2-09, #231)** |
| `PUT /stokvels/{id}/members/me/beneficiary` | Member | Choose the beneficiary, and so the payout currency, for the next cycle. **Built (R2-09, #231)** |
| `POST /stokvels/{id}/cycles` | Organiser | Start a cycle (needs at least 2 ready members, every one with a beneficiary). **Built (R2-10, #232)**, with the round schedule in the request |
| `POST /stokvels/{id}/members/me/continuation` | Member | Continue or leave after a cycle ends. **Built (R2-15, #237)** |
| `POST /stokvels/{id}/contributions` | Member | Contribute to the current round. **Built (R2-11, #233).** No body: the API takes the open round (the first round without a contribution from every member, the contract's `openRound` rule) and the stokvel's fixed amount, charges the member at the live rate, and answers 201 with the `pending` contribution (`StokvelContributionRead`: `contribution_id`, `stokvel_id`, `cycle_number`, `round`, `status`, `currency`, `amount_token`, `amount_fiat`, `fee_amount` (the member's fee share, D6), `amount_zar`, `created_at`). The member's account must cover `amount_fiat` + `fee_amount`. Refusals in section 6 |
| `GET /stokvels/{id}` | Member | Member screen data. **Built (R2-14, #236)** |
| `POST /stokvels/{id}/cover` | Member | Set the stokvel's cover photo. **Built.** The body is the file (JPEG, PNG or WebP, at most 5 MB). Any current member may replace it |
| `GET /admin/stokvel-contract` | `stokvel:contract:pause` | **Built.** Vault address, network label, on-chain `paused`, `paused_at` and `paused_reason` from the latest pause audit entry, treasury UCTUSD balance |
| `POST /admin/stokvel-contract/pause` and `/unpause` | Administrator | Emergency stop and resume. Pause takes a required `reason` in the request body |
| `GET /admin/stokvels/rounds` | `stokvel:round:finalise` | **Built.** Each active registered cycle's next unreleased round (paid counts, payout time, release status) |
| `POST /admin/stokvels/{id}/rounds/{n}/finalise` | `stokvel:round:finalise` (compliance officer) | **Built (R3-10, #247).** Manual fallback (P5). See below |
| `POST /admin/stokvels/{id}/cancel` | Administrator | Cancel. **Not in v1** (P4). Takes a required `reason` in the request body |

### Create and list stokvels (R2-07, built)

Customer routes, tag `stokvels` (client: `api.stokvels.createStokvel`, `api.stokvels.listStokvels`). `frontend/openapi.json` has the exact schemas.

**`POST /stokvels`** → `201 StokvelRead`. Request `StokvelCreateRequest`, unknown fields refused:

| Field | Rule |
|---|---|
| `name` | Trimmed, 1 to 80 characters |
| `currency` | The Stokvel currency: `ZAR`, `USD`, `ZWL` or `NAD`. The caller must already hold a fiat account in it |
| `contribution_amount` | Fixed UCTUSD amount per round for the stokvel's life (D13); greater than 0, at most 8 decimal places |

In one transaction: the stokvel, its `STOKVEL` ledger account (section 3) and the Organiser's `stokvel_members` row (their account in the Stokvel currency, `invitation_id` null). Nothing goes on-chain: `createStokvel` is sent when the first cycle starts (R2-10).

| Status | When |
|---|---|
| 401 | Not signed in |
| 403 | The caller is not KYC-verified (`KycNotApprovedToCreateStokvelError`) |
| 400 | The caller holds no account in `currency` (`StokvelCurrencyAccountMissingError`); they open one with `POST /accounts` first. 400 as for the beneficiaries' `PayoutAccountMissingError` |
| 422 | Invalid name, currency or amount, or an unknown field |

**`GET /stokvels`** → `200 StokvelListRead`: `{stokvels, invitations}`, each newest first.

- `stokvels`: those the caller is a current member of (left ones are not listed). `StokvelRead`: `stokvel_id`, `name`, `currency`, `contribution_amount` (UCTUSD, 8 dp string), `is_organiser`, `member_count` (current members), `max_members` (`MAX_STOKVEL_MEMBERS`), `created_at`, `deactivated_at`, `cover_url` (a short-lived read URL for the cover photo, or null).
- `invitations`: the caller's pending ones, leaving out invitations to a deactivated stokvel (they cannot be accepted; R2-08). `StokvelInvitationRead`: `invitation_id`, `stokvel_id`, `stokvel_name`, `currency`, `contribution_amount`, `invited_by_name` ("Tendai M."), `created_at`. No member count: an invitee cannot read the member rows under row-level security, so it would always read 0 on Postgres.
- Both lists are filtered by the caller in the query, not only by row-level security, so SQLite (tests) returns the same rows as Postgres.

### One stokvel (R2-14, built)

Customer route, tag `stokvels` (client: `api.stokvels.getStokvel`).

**`GET /stokvels/{id}`** → `200 StokvelDetailRead`. `StokvelRead`, plus the current cycle (`StokvelDetailCycleRead`; `StokvelCycleRead` is what `POST /stokvels/{id}/cycles` returns), its members, pending invitations, contributions and rounds. While the current cycle is forming and follows a closed one, `previous_cycle` is that closed cycle, in the same shape, so each round's release status, hashes and remittance stay on the screen after the worker opens the next cycle (brief §2 step 6; R2-15, #237). It is null otherwise, and carries no contributions. A caller who is not a current member gets 404, the same answer as an unknown id.

- `organiser_name`, `members[].full_name` and a beneficiary's `full_name` are `short_display_name` ("Tendai M."), or null when there is no first name.
- `members[].in_cycle`: the member has a row in the current cycle. From cycle 2, while it is forming (`previous_cycle` set), that is the Organiser, those who chose to continue and anyone who joined since; false for a member who hasn't answered. The Organiser's setup orders only these, and a member's own value says whether they still have to choose (R4-10, #259).
- `contribution_fiat_estimate` is today's rate, to the cent. Null when no rate is available; the rest of the response still returns.
- `phase` is the current cycle's status (`StokvelCycleStatus`), or `forming` when the stokvel has no cycle. `current_round` is that cycle's stored column (0 at start). `open_round` is the round a contribution joins, from `StokvelContributionRepository.open_round`: the first round with fewer non-failed contributions than the cycle's locked members, and `total_rounds` is the round count. It is null while the cycle is not active, and null once every round is full. `total_rounds` and `next_payout_time` follow `current_round`. `current_round`, `total_rounds` and `next_payout_time` are null while the cycle is forming. `open_round` is null then too. Rounds exist only after the cycle starts (#232). `registered_at` is null until that start is mined; `phase` is already `active` by then, and contributions answer 409 `cycle_starting` until it is set. Contribution `status` and `my_contribution_status` are `StokvelContributionStatus`. A round's `release_status` is `StokvelPayoutReleaseStatus` and its `remittance_status` is `TransactionStatus`, null until `remittance_id` is set.
- `my_member_id` is the caller's `stokvel_members.id`. `payout_order` is those ids from position 0, stopping at the first gap. A round past that gap has no `recipient_member_id`.
- Invitations on this response are `StokvelDetailInvitationRead`: every invitation of the stokvel, of any status (`pending`, `accepted`, `declined`, `revoked`, `lapsed`), newest first (`created_at` descending, then `id`; R2-17, #375). `account_reference` is set only for the Organiser, for every status. Other members get null, and `accounts` is not read for them. `POST /stokvels/{id}/invitations` still returns `SentStokvelInvitationRead`, whose `account_reference` is always set.
- `fee_amount` is set only on the caller's own contributions, from their fee leg. Other rows are null.
- `remittance_id` is the payout reference. `remittance_status` is null until that id is set, because the column is `pending` from the moment the payout row exists. `pool_fiat_amount` is null until members can read the payout quote (#241).
- `my_contribution_status` is the caller's contribution to the stored `current_round` that has not failed, or null. It does not follow `open_round`.

| Status | When |
|---|---|
| 401 | Not signed in |
| 404 | Unknown stokvel, or the caller is not a current member (`StokvelNotFoundError`) |

**`POST /stokvels/{id}/cover`** → `200 StokvelCoverRead`: `cover_url`, a short-lived read URL for the photo just stored. The body is the file itself, with its own `Content-Type` (`image/jpeg`, `image/png` or `image/webp`). The type is taken from the leading bytes, and the declared type has to agree. At most 5 MB. Any current member may set it, and a later upload replaces it: one object, `stokvel-covers/<stokvel id>`. The list and the member screen show that photo with the stokvel's name over a gradient (`api.stokvels.uploadStokvelCover`). `cover_url` on `StokvelRead` is null when there is no photo, when the stored key is not that fixed key, or when the bucket cannot sign one; a missing bucket does not take the screen down.

| Status | When |
|---|---|
| 401 | Not signed in |
| 400 | Empty body, a type outside JPEG/PNG/WebP, or bytes that disagree with the declared type. An SVG is named in the refusal |
| 404 | Unknown stokvel, or the caller is not a current member (`StokvelNotFoundError`), including a former member |
| 409 | The stokvel is deactivated (`stokvel_deactivated`), or the object did not store |
| 413 | Larger than 5 MB |
| 502, 503 | The bucket refused the write, or it is not configured |

The member screen calls `GET /stokvels/{id}` (`stokvelQueries.detail` → `sdk.stokvels.getStokvel`, R4-09 #258). The collecting round on that screen is the response field `open_round`. The screen does not recompute it. `current_round` stays the stored column. The list and this screen refetch every 3 seconds while open once a read has succeeded, and keep that read on screen if a later one fails. While any of the caller's contributions is pending or processing, this screen asks every 1.5 seconds. The admin rounds page refetches every 3 seconds the same way. `fee_amount` is null on other members' rows. The reference shown is `remittance_id`. `pool_fiat_amount` is null, so the screen estimates the pool as members × `contribution_fiat_estimate` when that estimate exists. `organiser_name`, member and beneficiary names, and `contribution_fiat_estimate` can be null. While the cycle is forming, `current_round`, `total_rounds` and rounds are null or empty. The response has no per-member beneficiary flag: the setup screen only knows the caller's `my_beneficiary`. Another member who has not chosen one is reported as `cycle_not_ready` when the Organiser starts the cycle. Demo ids (`stk_…`) are gone with `stokvels.mock.ts`. The admin contract page reads `GET /admin/stokvel-contract` when it is opened and after pause or resume; it does not poll, because each read calls the chain.

### Invitations (R2-08, built)

Customer routes, tag `stokvels` (client: `api.stokvels.inviteToStokvel`, `api.stokvels.acceptStokvelInvitation`, `api.stokvels.declineStokvelInvitation`). Nobody becomes a Member without accepting; row-level security holds the same rule (section 3). Refusal codes and wording are in section 6.

**`POST /stokvels/{id}/invitations`** → `201 SentStokvelInvitationRead`: `invitation_id`, `stokvel_id`, `invitee_name` ("Thandi M.", or null), `account_reference`, `status` (`pending`), `created_at`. Request `StokvelInvitationCreateRequest`: exactly one of `account_reference` (trimmed, 1 to 64 characters) and `beneficiary_id` (one of the Organiser's beneficiaries), else 422; unknown fields refused. The invitee is the owner of that account, which must be in the Stokvel currency, or the person the beneficiary links to, paying from their account in the Stokvel currency (none: 422 `invitee_currency_mismatch`). Someone else's or an unknown `beneficiary_id` is 404 `Beneficiary not found`, as on the beneficiary routes. The member screen invites from the Organiser's beneficiaries, or by account reference for someone who isn't one. Invitations may outnumber the free places: the cap holds at accepting, and is checked here only to refuse early.

**`POST /invitations/{id}/accept`** → `200 StokvelRead`, the stokvel joined. In one transaction, holding the `stokvels` row (`SELECT ... FOR UPDATE`): re-check the caller's KYC, find their account in the Stokvel currency, count current members against `MAX_STOKVEL_MEMBERS`, set the invitation to `accepted` (guarded by `status = 'pending'`; `status_changed_by_user_id` = the invitee), then insert their `stokvel_members` row (`account_id`, `invitation_id`). The status changes first because the insert policy requires an accepted invitation.

**`POST /invitations/{id}/decline`** → `204`. Sets the invitation to `declined` (same guard). The Organiser may invite them again.

**`POST /invitations/{id}/revoke`** → `204`. The Organiser sets a pending invitation to `revoked` (same guard; `status_changed_by_user_id` = the Organiser). The invitee may be invited again. Allowed on a deactivated stokvel.

| Status | When |
|---|---|
| 401 | Not signed in |
| 404 | Unknown stokvel, or one the caller is not the Organiser or a current member of; unknown account reference; unknown invitation, or one the caller can neither answer nor see as a fellow member |
| 403 | Not the Organiser (invite); not the invitee (accept, decline); invitee not verified (invite); caller no longer verified (accept) |
| 400 | The caller's own reference (invite); no account in the Stokvel currency (accept, `StokvelCurrencyAccountMissingError`) |
| 409 | Already a member; already a pending invitation; stokvel deactivated; invitation no longer pending |
| 422 | Account not in the Stokvel currency; stokvel full; invalid request body |

### Payout order and beneficiary (R2-09, built)

Customer routes, tag `stokvels` (client: `api.stokvels.setPayoutOrder`, `api.stokvels.setMyBeneficiary`), in `StokvelSetupController`. Both work on the stokvel's `forming` cycle, can be repeated as often as needed, and are refused once the cycle has started. Each holds the `stokvels` row lock (`SELECT ... FOR UPDATE`), as accepting an invitation does. Refusal codes and wording are in section 6.

**`PUT /stokvels/{id}/payout-order`** → `200 StokvelPayoutOrderRead`: `stokvel_id`, `cycle_number`, `order` (`member_id`, `payout_position` (0-based), `name` ("Thandi M.", or null)), first paid first. Request `StokvelPayoutOrderRequest`: `member_ids`, at least one, unknown fields refused. `member_ids` are `stokvel_members.id` (the on-chain `memberId`) and must be every current member exactly once; `member_ids[i]` is paid in round i. The new order replaces the old in place: every position in the cycle is cleared, then rewritten, so a member who has left keeps their row with no position.

**`PUT /stokvels/{id}/members/me/beneficiary`** → `200 StokvelBeneficiaryRead`: `stokvel_id`, `cycle_number`, `member_id`, `beneficiary_id`, `payout_currency`. Request `StokvelBeneficiaryRequest`: `beneficiary_id`, unknown fields refused. It must be one of the caller's own beneficiaries. The payout currency is the beneficiary's own, copied onto the caller's cycle row once the recipient is confirmed to still hold a fiat account in it (as when the beneficiary was added), so changing the beneficiary later does not move a choice already made. From cycle 2 this gives the caller a row in the forming cycle, so it counts as continuing: their closed row's `continued` becomes true, as for `POST /members/me/continuation`.

A stokvel created before cycles opened at creation has none: the Organiser's first call to either route opens cycle 1, with a row for every current member. A member with no row gets one. A member who is not the Organiser cannot open the cycle (row-level security), so gets 409 `cycle_not_forming` until the Organiser does.

| Status | When |
|---|---|
| 401 | Not signed in |
| 404 | Unknown stokvel, or one the caller is not a current member of; a beneficiary that is unknown or not the caller's |
| 403 | Not the Organiser (payout order) |
| 400 | The recipient no longer holds an account in the beneficiary's payout currency (`PayoutAccountMissingError`) |
| 409 | Stokvel deactivated; the cycle has started; no `forming` cycle to set up |
| 422 | Payout order not every current member exactly once; invalid request body |

### Start a cycle (R2-10, built)

Customer route, tag `stokvels` (client: `api.stokvels.startStokvelCycle`), in `StokvelCycleController`. The round schedule is sent here, when the Organiser starts the cycle (it answers the section 8 question): `stokvel_rounds` hangs off a cycle, and the payout order it pairs with is only final now.

**`POST /stokvels/{id}/cycles`** → `201 StokvelCycleRead`: `stokvel_id`, `cycle_id`, `cycle_number`, `status` (`active`), `total_rounds`, `current_round` (0), `started_at`, `registered_at` (null until the worker's `startCycle` is mined), `rounds` (`round`, `start_time`, `deadline`, `payout_time`), `order` (`member_id`, `payout_position`, `beneficiary_id`, `payout_currency`, first paid first), `lapsed_invitations`. Request `StokvelCycleStartRequest`: `rounds`, 2 to 255 of `{start_time, deadline, payout_time}`, each with an offset (a time without one is refused) and none before 1970 (the contract takes `uint64` seconds), unknown fields refused. Times are stored in UTC to the whole second.

Checks, in order, mirroring `startCycle` (section 1) so the contract accepts what starts here: a current member (else 404), the Organiser, not deactivated, a `forming` cycle; at least 2 (`MIN_MEMBERS`) and at most `MAX_STOKVEL_MEMBERS` current members; every current member has a cycle row with a payout position and a beneficiary, and the positions are exactly `0..n-1` (section 8); one round per member; start ≤ deadline ≤ payout within a round; start and payout times never go backwards (equal allowed).

In one transaction, holding the `stokvels` row lock as the setup routes and accepting an invitation do: write the rounds; lapse every pending invitation (`status_changed_by_user_id` = the Organiser); lock the current members' cycle rows (a former member's row stays unlocked); the cycle becomes `active` with `started_at`, `total_rounds` and `current_round` 0. After the commit, `stokvel.start_cycle` is queued (section 4); a lost enqueue is logged and the start still answers 201, since the cycle is committed and `stokvel.register_started_cycles` queues it later. The fixed token contribution needs nothing: it is the stokvel's `contribution_amount` (D13). Contributions answer 409 `cycle_starting` until `registered_at` is set.

| Status | When |
|---|---|
| 401 | Not signed in |
| 404 | Unknown stokvel, or the caller is not a current member |
| 403 | Not the Organiser |
| 409 | Stokvel deactivated; no `forming` cycle; the cycle has started; fewer than 2 members; a member without a place in the payout order or a beneficiary, or the members changed since the order was set |
| 422 | More members than `MAX_STOKVEL_MEMBERS`; the wrong number of rounds, or times out of order; invalid request body |

### Continue or leave after a cycle (R2-15, built)

Customer route, tag `stokvels` (client: `api.stokvels.continueOrLeaveStokvel`), in `StokvelSetupController`. Allowed while the stokvel's next cycle is `forming`, under the `stokvels` row lock as the setup routes take it. Refusal codes and wording are in section 6.

**`POST /stokvels/{id}/members/me/continuation`** → `200 StokvelContinuationRead`: `stokvel_id`, `cycle_number` (the next cycle), `member_id`, `choice`, `beneficiary_id` and `payout_currency` (null on leaving, or for a member continuing who has never chosen one). Request `StokvelContinuationRequest`: `choice` (`continue` or `leave`) and, only when continuing, an optional `beneficiary_id`; unknown fields refused.

- **Continue:** the caller gets a row in the next cycle, with no payout position. With `beneficiary_id`, it is checked as for `PUT /members/me/beneficiary`; without one, the choice already on the row is kept, else the closed cycle's is carried over. Their closed row's `continued` becomes true. Repeatable, to change the beneficiary
- **Leave:** `left_at` is set (final: coming back needs a new invitation), the closed row's `continued` becomes false, and any position on the next cycle's row is cleared. A member who continued may still leave
- **The Organiser** is continued when the next cycle opens and may call this to change their beneficiary; leaving is refused. Getting out means closing the stokvel for everyone (section 8)
- **Not choosing:** when the Organiser starts the next cycle (`POST /stokvels/{id}/cycles`), a member of the closed cycle with no row in it is treated as leaving, in the same transaction (`left_at`, `continued` false)

From cycle 2, `PUT /payout-order` must name exactly the members going in (the Organiser, those who continued, and anyone who joined since), and `POST /cycles` counts and checks only them.

| Status | When |
|---|---|
| 401 | Not signed in |
| 404 | Unknown stokvel, or the caller is not a current member (a member who has left included); a beneficiary that is unknown or not the caller's |
| 400 | The recipient no longer holds an account in the beneficiary's payout currency (`PayoutAccountMissingError`) |
| 409 | Stokvel deactivated; no cycle has finished yet; the next cycle has started; the next cycle is not open (a member who is not the Organiser, after a cycle that closed before R2-15); the Organiser leaving |
| 422 | Invalid request body, including a `beneficiary_id` with `leave` |

### Manual finalise (R3-10, built)

Admin route, tag `admin.stokvels` (client: `api.admin.stokvels.finaliseStokvelRound`). Permission `stokvel:round:finalise`, granted to the compliance officer. No request body.

**`POST /admin/stokvels/{id}/rounds/{n}/finalise`** → `202 StokvelRoundFinaliseResponse`: `stokvel_id`, `cycle_id`, `cycle_number`, `round` (0-based, the path's `n`). The round is the open cycle's. When that cycle has closed, including when the worker has already opened the next one as `forming` (R2-15, #237), the route does not read the vault: a round the closed cycle had answers 409 `round_already_finalised` (the contract closes a cycle only after its last round is released), and a round past `total_rounds` answers 409 `round_not_finalisable`. A payout row that is `released` answers 409 `round_already_finalised`, and one that is `processing` or `failed` answers 409 `round_release_not_pending`, before any other check of that round. The database then applies D5 and D12 (payout time passed, and every member confirmed for this round and the next unless it is the last) and answers 409 `round_not_finalisable` when those fail; that check does not replace the payout-status codes. Otherwise the API reads the vault (`isFinalisable`, and `getCycle` when that is false, so an already released round is told apart from one that is not ready). A ready round whose payout is `pending` or missing records `stokvel.round.finalised_manually` and then queues `stokvel.release_pool` (section 4) in that same transaction, enqueue last, so a failed enqueue rolls the audit back. A crash after the queue is sent and before the commit can still release with no audit row. The worker sends `finalise` and records the release; this route does not wait for the hash. The audit records the cycle, the round, the payout's release status and transaction hash if a payout row already has them, and `enqueued: true`.

A payout left `processing` or `failed` answers 409 `round_release_not_pending` and queues nothing. `release_pool` only claims `pending`, and handing a `processing` claim back could pay the round twice. A registered cycle the vault does not have open (or a vault that does not know the stokvel) answers 503 `stokvel_chain_mismatch` and is logged as `stokvel.finalise_chain_mismatch`. That is not `cycle_starting`: `cycle_starting` is only while `registered_at` is null.

A second call while the chain still says the round is ready, and the payout is still `pending`, queues the task again. That does not release twice: `release_pool` claims the payout once, and `record_pool_release` books the leg once (section 4). Once the chain says the round is released, the route answers 409 and queues nothing.

The admin contract page calls `GET /admin/stokvel-contract` and the pause and unpause POSTs. The admin rounds page calls `GET /admin/stokvels/rounds` and the finalise POST (client: `api.admin.stokvel_contract.*`, `api.admin.stokvels.*`).

| Status | When |
|---|---|
| 401 | Not signed in |
| 403 | Missing `stokvel:round:finalise` |
| 404 | Unknown stokvel |
| 409 | No cycle, or the open one is not active (`cycle_not_open`); the cycle is not on the chain yet (`cycle_starting`); the round is not ready, or is past a closed cycle (`round_not_finalisable`); the round is already released, including a round of a closed cycle (`round_already_finalised`); the payout is `processing` or `failed` (`round_release_not_pending`) |
| 422 | `n` is outside 0..255 |
| 503 | The vault is paused (`stokvel_paused`); a registered cycle does not match the vault (`stokvel_chain_mismatch`); the vault cannot be read |

### Audit log of admin actions

Admin actions on stokvels are recorded in the **existing** audit log (`audit_log`, written only through `audit_service.record_audit`, append-only, read through `GET /admin/audit` with `audit:read`). No new table is needed: action strings are free text in the database, and the `AuditAction` and `AuditSubject` enums in `models/orm/audit_log.py` gain new members. The entry is staged in the same transaction as the action, as for every other audit entry, and never contains PII: ids, round numbers, statuses and transaction hashes only.

| Admin action | Audit action | Subject type | Subject id | Recorded in `before` / `after` |
|---|---|---|---|---|
| Pause the contract | `stokvel.contract.paused` | `stokvel_contract` | `STOKVEL_CONTRACT_SUBJECT_ID` | paused flag; `reason` required |
| Resume the contract | `stokvel.contract.unpaused` | `stokvel_contract` | `STOKVEL_CONTRACT_SUBJECT_ID` | paused flag |
| Manual finalise (P5) | `stokvel.round.finalised_manually` | `stokvel` | stokvel id | cycle number, round, release status, transaction hash if a payout row has one, `enqueued` |

Cancellation is not an action: P4 is not in v1 (#208), so there is no `stokvel.cancelled`.

- Only actions by a real staff member are logged here (`actor_user_id` is never null). The automatic release, event sync and refund tasks are system actions; their trail is the ledger, `stokvel_payouts` and the contract events.
- Filter `GET /admin/audit` by `subject_type=stokvel` or `stokvel_contract`.
- The admin audit page gets a stokvel filter (R4-12). Pause (R3-07) and manual finalise (R3-10) write these entries.

The admin finalise route removed from an earlier draft is back as a fallback only (P5). Finalisation is still automatic by default (D5).

_TBD per endpoint: request and response shape, errors._

---

## 6. Error mapping

| Contract error | API status and code | Message shown to the user |
|---|---|---|
| `AlreadyPaid` | 409 `contribution_already_paid` | "You've already paid for this round." |
| `NotMember` | 403 `not_a_member` | "You're not a member of this stokvel's current cycle." |
| `WrongRound` | 409 `wrong_round` | "This round isn't open for contributions." |
| `WrongAmount` | 500 `contribution_amount_mismatch` | "Something went wrong. Please try again." (backend bug, not user error) |
| `NotYetFinalisable` | 409 `round_not_finalisable` | "This round can't be paid out yet." |
| `AlreadyFinalised` | 409 `round_already_finalised` | "This round has already been paid out." |
| `CycleNotOpen` (was `CycleClosed`) | 409 `cycle_not_open` | "This stokvel has no active cycle right now." Raised both before the first cycle starts and after a cycle closes, so the wording is neutral; the API can use `getStokvel` to say which |
| `MaxMembersExceeded` | 422 `too_many_members` | "A stokvel can have at most {max} members." |
| OpenZeppelin `EnforcedPause` | 503 `stokvel_paused` | "Stokvels are temporarily paused." |
| Token `ERC20InsufficientAllowance` (from UCTUSD, not the vault) | 500 `treasury_allowance_missing` | "Something went wrong. Please try again." (backend fault: re-approve, see section 1 "Treasury allowance") |
| Token `ERC20InsufficientBalance` (from UCTUSD: the Treasury Wallet has run out of UCTUSD) | 503 `treasury_funds_low` | "Contributions are temporarily unavailable. Please try again later." (operations fault: top up the Treasury; alert the operator. The likeliest failure on testnet. Confirmed on the live token, 2026-10-09) |

**Refusals for manual finalise (R3-10)** that are not a contract revert. `NotYetFinalisable` and `AlreadyFinalised` above still apply. `cycle_starting` is only while `registered_at` is null.

| Case | API status and code | Message shown to the user |
|---|---|---|
| The payout is `processing` or `failed` | 409 `round_release_not_pending` | "This round's payout is already in progress or has failed, so it can't be queued again." |
| The cycle is registered, but the vault has no open cycle for it or does not know the stokvel | 503 `stokvel_chain_mismatch` | "This stokvel's records don't match the contract. An operator needs to check the vault before this round can be paid out." |

**Refusals the API raises before anything goes on-chain (R2-11, `POST /stokvels/{id}/contributions`):** the API checks the contract's `NotMember`, `CycleNotOpen`, `WrongRound` and `AlreadyPaid` rules itself and answers with the codes above. It also answers:

| Case | API status and code | Message shown to the user |
|---|---|---|
| No such stokvel, or the caller is not a current member of it (an outsider, a pending invitee, a member who left) | 404, no code | "Stokvel not found." The same answer for both, so an id reveals nothing; on Postgres, row-level security hides the stokvel from outsiders anyway. `not_a_member` (403) is only for a current member outside the open cycle |
| Balance does not cover the contribution plus the fee share | 400, no code | "Your available {currency} balance is {available}, and this contribution needs {needed}. Top up your {currency} account first." |
| Member not KYC-verified | 403, no code | The existing `KycNotApprovedError` message (`require_can_send`) |
| Over the member's daily or monthly limit, contributions and remittances together (D8) | 400, no code | The existing `LimitExceededError` message (`require_can_send`) |
| No usable exchange rate (the live fetch failed and no stored rate is recent enough) | 503, no code | "Exchange rate unavailable; try again shortly", as for a quote. Nothing is recorded |

**In the worker (R2-12):** a contribution is sent after the API has answered, so these errors never reach the member as a status. `stokvel.submit_contribution` fails the contribution on a rule refusal and retries on the platform's faults: `EnforcedPause`, the Treasury's token errors (`ERC20InsufficientBalance`, `ERC20InsufficientAllowance`), `AccessControlUnauthorizedAccount` (the Treasury without `OPERATOR_ROLE`) and `SafeERC20FailedOperation`, and on a send or `approve` the RPC refused (section 4). The member sees the contribution `failed` (and may pay again) or, eventually, `confirmed`.

**Refusals for invitations (R2-08, R2-16):** `MaxMembersExceeded`'s `too_many_members` above is also the API's answer when the stokvel is full, checked when inviting and holding at accepting. The rest are the API's own:

| Case | API status and code | Message shown to the user |
|---|---|---|
| A member who is not the Organiser invites | 403 `not_organiser` | "Only the stokvel's organiser can invite members." |
| Invitee not KYC-verified | 403 `invitee_not_verified` | "This person isn't verified yet, so they can't be invited." |
| Invitee's account not in the Stokvel currency | 422 `invitee_currency_mismatch` | "The account's currency must match the stokvel's currency ({currency})." |
| Invitee already a current member | 409 `already_a_member` | "This person is already a member of the stokvel." |
| Invitee already has a pending invitation (`uq_stokvel_invitations_pending`) | 409 `invitation_already_pending` | "This person already has a pending invitation." |
| Stokvel deactivated | 409 `stokvel_deactivated` | "This stokvel is no longer active." |
| A fellow member answers someone else's invitation | 403 `not_invitee` | "Only the person invited can answer this invitation." |
| The invitee or a fellow member revokes an invitation (R2-16) | 403 `not_organiser` | "Only the stokvel's organiser can revoke invitations." |
| Invitation already accepted, declined, revoked or lapsed | 409 `invitation_not_pending` | "This invitation has already been answered or has expired." |
| Unknown stokvel, reference or invitation, or one the caller cannot see | 404, no code | "Stokvel not found.", "No account has the reference '{reference}'.", "Invitation not found." |
| The Organiser's own reference | 400, no code | "You can't invite yourself." |
| Accepting with no account in the Stokvel currency | 400, no code | `StokvelCurrencyAccountMissingError`'s message, as for `POST /stokvels` |
| Accepting after the caller's verification lapsed | 403, no code | "Only verified customers can join a stokvel. Finish verification to continue." |

**Refusals for the payout order and beneficiary (R2-09):**

| Case | API status and code | Message shown to the user |
|---|---|---|
| A member who is not the Organiser sets the payout order | 403 `not_organiser` | "Only the stokvel's organiser can set the payout order." (`NotStokvelOrganiserError` now takes the action; the invite wording is unchanged) |
| The cycle has started | 409 `cycle_locked` | "The payout order and beneficiaries are locked while a cycle is running." |
| No `forming` cycle, and the caller is not the Organiser (who opens it): a stokvel with no cycle yet, or one whose last cycle closed before the worker opened the next (R2-15) | 409 `cycle_not_forming` | "This stokvel's next cycle hasn't been opened yet." |
| The payout order repeats a member | 422 `invalid_payout_order` | "Each member can appear only once in the payout order." |
| The payout order names a member who has left | 422 `invalid_payout_order` | "The payout order includes a member who has left the stokvel." |
| The payout order names someone who is not a member of this stokvel | 422 `invalid_payout_order` | "The payout order includes someone who isn't a member of this stokvel." |
| The payout order leaves out a current member | 422 `invalid_payout_order` | "The payout order must include every current member." |
| From cycle 2: the payout order names a member of the closed cycle who has not chosen to continue (R2-15) | 422 `invalid_payout_order` | "The payout order includes a member who hasn't chosen to continue into the next cycle." |
| From cycle 2: the payout order leaves out a member going into the cycle (R2-15) | 422 `invalid_payout_order` | "The payout order must include every member continuing into the next cycle." |
| Stokvel deactivated | 409 `stokvel_deactivated` | "This stokvel is no longer active." |
| Unknown stokvel, or the caller is not a current member | 404, no code | "Stokvel not found." |
| Beneficiary unknown or not the caller's | 404, no code | "Beneficiary not found", as for the beneficiary routes |
| The recipient no longer holds the payout-currency account | 400, no code | `PayoutAccountMissingError`'s message, as when adding a beneficiary |
| `DELETE /beneficiaries/{id}` on a beneficiary any stokvel cycle row pays (forming, active or closed) | 409 `beneficiary_in_use_by_stokvel` | "A stokvel pays this beneficiary. Choose a different beneficiary for that stokvel before removing this one." |

**Refusals for starting a cycle (R2-10):** the API checks `startCycle`'s rules itself, so these never reach the contract. `TooFewMembers` and `CycleInProgress` get codes of their own; `MaxMembersExceeded`'s `too_many_members` above is reused; `ScheduleLengthMismatch` and `InvalidSchedule` are `invalid_schedule`.

| Case | API status and code | Message shown to the user |
|---|---|---|
| A member who is not the Organiser starts the cycle | 403 `not_organiser` | "Only the stokvel's organiser can start a cycle." |
| The cycle has already started (`CycleInProgress`) | 409 `cycle_in_progress` | "This stokvel's cycle has already started." |
| No `forming` cycle | 409 `cycle_not_forming` | "This stokvel's next cycle hasn't been opened yet." |
| Fewer than 2 current members (`TooFewMembers`) | 409 `too_few_members` | "A cycle needs at least 2 members." |
| A current member has no place in the payout order | 409 `cycle_not_ready` | "Set the payout order for every current member first." |
| The positions are not `0..n-1` (a member left or joined since the order was set) | 409 `cycle_not_ready` | "The members have changed since the payout order was set. Set it again." |
| A current member has no beneficiary | 409 `cycle_not_ready` | "Every member must choose a payout beneficiary first." |
| More members than `MAX_STOKVEL_MEMBERS` (`MaxMembersExceeded`) | 422 `too_many_members` | "A stokvel can have at most {max} members." |
| Not one round per member (`ScheduleLengthMismatch`) | 422 `invalid_schedule` | "Give one round for each of the {n} members, in payout order." |
| A round's times out of order (`InvalidSchedule`) | 422 `invalid_schedule` | "Round {n}: the start time, deadline and payout time must be in that order." |
| A round starts or pays out before the one before it (`InvalidSchedule`) | 422 `invalid_schedule` | "Round {n} can't start or pay out before the round before it." |
| Stokvel deactivated | 409 `stokvel_deactivated` | "This stokvel is no longer active." |
| Unknown stokvel, or the caller is not a current member | 404, no code | "Stokvel not found." |

**Refusals for continuing or leaving after a cycle (R2-15):**

| Case | API status and code | Message shown to the user |
|---|---|---|
| No cycle has finished: the forming cycle is the stokvel's first | 409 `nothing_to_continue` | "There's no finished cycle to continue from yet." |
| The Organiser chooses to leave | 409 `organiser_cannot_leave` | "As Organiser you can't leave. Closing the stokvel ends it for everyone." |
| The next cycle has started | 409 `cycle_locked` | As for the setup routes |
| The next cycle is not open yet (a member who is not the Organiser) | 409 `cycle_not_forming` | As for the setup routes |
| Stokvel deactivated | 409 `stokvel_deactivated` | "This stokvel is no longer active." |
| Unknown stokvel, or the caller is not a current member | 404, no code | "Stokvel not found." |
| Beneficiary unknown or not the caller's | 404, no code | As for the setup routes |
| The recipient no longer holds the payout-currency account | 400, no code | `PayoutAccountMissingError`'s message |

From cycle 2, the start's member counts (`too_few_members`, `too_many_members`) and `cycle_not_ready` count only the members going into the cycle.

**And for contributing (R2-10):** a started cycle that the worker has not registered on-chain yet answers `POST /stokvels/{id}/contributions` with 409 `cycle_starting`, "This stokvel's cycle is still being set up. Try again in a minute." (the contract would refuse it `CycleNotOpen`).

_Roles 1, 2 and 4 to confirm codes and wording._

**Error body (R2-11):** `{"detail": "<message>", "code": "<code>"}`. `code` is present only on refusals that have one (`DomainError.code`), so the frontend can tell the 409s apart; every other refusal is `{"detail": ...}` as before. `ErrorResponse` in the OpenAPI spec has `code` as an optional field (absent when the refusal has none), so the generated client knows it. `POST /stokvels/{id}/contributions` also refuses, without a code, as `POST /remittances` does: a short available balance (400), a contribution over the daily or monthly limit (400), and a caller who is not verified (403). An unknown stokvel is 404. No usable exchange rate is 503, as for a quote, and nothing is recorded.

---

## 7. TrustMeBank touchpoints (Role 5)

TrustMeBank is an optional extension in the brief, but this build treats it as required (#202 and #203 are core tickets). It provides the fiat in and out: deposits authorised through TrustMeBank (#202) and withdrawals paid out through it (#203). It replaces CSV reconciliation as an additional path. Stokvel contributions draw from the member's existing fiat account, so the stokvel path does not depend on it.

- Webhook endpoint: _TBD_
- Events handled: _TBD_
- Deposit statuses: _TBD_
- How a completed payment links to a deposit record: _TBD_

Today TrustMeBank exists only in documents; the code reconciles CSV statements in `services/deposit_service.py`.

---

## 8. Open questions

| Question | Status | Owner | ADR |
|---|---|---|---|
| One Treasury Wallet, or a separate settlement wallet for pool release (#207)? D2 chooses one wallet; the wallet has been created. Confirm | **Resolved (2026-10-25):** one wallet (D2). #207 is closed, and contributions, pool releases and payouts all go through the one Treasury Wallet | Role 1, Product | |
| Which way does the `stokvel_pool_release` leg book? | **Resolved (2026-10-16, R2-11, #340):** `STOKVEL` account → Treasury Wallet, as contributions book Treasury → `STOKVEL`, so a `STOKVEL` balance always equals that stokvel's unreleased pools in the contract (section 3, "Ledger changes"; section 11). `stokvel_payouts.release_tx_id` names that leg | Roles 2, 3 | 0004 |
| Burn method (#206): does UCTUSD have a `burn()` function, or do we transfer to a dead address? Check the token on the explorer | **Confirmed (2026-10-14, #278):** `burn(uint256)` called by the Treasury Wallet. A test burn of 1 base unit, tx [`0xacfd…9cd6`](https://explorer.testnet.xrplevm.org/tx/0xacfd84b642ff7d30b535bf8256fc572657d54894a444e13039c212d4d68f9cd6) (block 9072949), lowered `totalSupply` from 99999990000000000000000000 to 99999989999999999999999999 base units, and the Treasury balance by the same 1. No dead-address transfer, and no `approve` (unlike `burnFrom`). Not a proxy, and no burner role in the bytecode. The worker burns through `evm_service.burn_tokens` | Role 1 | |
| Contract IDs: pack the database UUID into `bytes32` (current section 1), or give each stokvel and member a separate generated `bytes32` ID (Katlego, #283 review)? The contract accepts either. Packing needs no extra column and lets event sync map an ID straight back to its row; a separate ID keeps on-chain IDs unrelated to the database | **Resolved (2026-10-25):** the packed UUID, as built and deployed: the contract takes the UUID's 16 bytes then 16 zeros (`evm_service.uuid_to_bytes32`, `uuidToBytes32` in the contract tests). Roles 1 and 2 agreed it for the MVP on 2026-10-09; changing it now would need a redeploy | Roles 1, 2 | |
| Contribution amount: fixed token amount or fixed fiat amount? If a fixed token amount, live exchange rates must be taken into account (proposal: member debit = token amount × live rate at contribution). Refunds return the original fiat amount entered | **Resolved (product, 2026-10-11): fixed token (D13).** `stokvels.contribution_amount` is the fixed UCTUSD amount set in `createStokvel` for all cycles; a new amount means a new stokvel (MVP). Member fiat debit = token amount × live rate at contribution. #298 (Treasury FX difference under fixed fiat) is closed as not needed | Product, Roles 2, 3 | |
| Per-cycle contribution amounts (move the amount into `startCycle`, so the Organiser can change it between cycles)? | Deferred: not in the MVP (2026-10-09). Within a cycle the amount is always fixed. An interface change and a redeploy if wanted later | Role 1, Product | |
| Admin (deployer) key for pause and unpause on the server: R3-07 (#244) must sign `pause()` with the **admin** key, not the Treasury key, and #277 does not cover storing it. Store it the same way as the Treasury key, or keep pause as a manual step run by the key holder? | Resolved (#244): `EVM_STOKVEL_ADMIN_ADDRESS` and `EVM_STOKVEL_ADMIN_KEY_ENCRYPTED` in the worker env, decrypted like the treasury; `stokvel.pause_contract` / `unpause_contract` | Roles 1, 3 | |
| New `STOKVEL_REMITTANCE` type, or reuse the existing remittance legs with the stokvel as the quote's sender (this doc's recommendation)? | **Resolved (2026-10-25, confirmed by Role 2; built in R3-05 #242 and R3-06 #243):** reuse the existing types, no new type. The stokvel is the quote's sender (`quotes.stokvel_id`, never with `sender_user_id`), and the four legs share its `quote_id`, so `settle_remittance` settles a payout as it does any send: `remittance` Treasury Wallet → beneficiary token account, `remittance` back to the Treasury Wallet, `token_burn`, and `beneficiary_payout`. The legs start from the Treasury Wallet, not from `STOKVEL`, because the pool left `STOKVEL` at its release. No fee leg and no fiat cash-in (D6). A payout is told apart from a customer send by `quotes.stokvel_id` or through `stokvel_payouts.quote_id` (section 3) | Roles 2, 3 | |
| Cancellation (P4): who may cancel, and does it reverse the brief's "refunds out of scope"? (#208) | **Resolved (product, 2026-10-09):** not in v1, nor refunds or disputes | Product | |
| When can `transactions.xrpl_tx_hash` be dropped? Once the R3-02 release is live everywhere, a migration copies any hash written only to the old column into `evm_tx_hash`, drops the column, and the worker stops writing it | Open: follow-up to R3-02 | Role 3 | |
| Which ledger leg does `stokvel_contributions.tx_id` name, and how are a contribution's legs grouped? Remittance legs share a `quote_id`; a contribution has no quote | **Resolved (2026-10-16, R2-11, agreed with Role 3):** the contribution row points at its legs through `fiat_tx_id`, `token_tx_id` and `fee_tx_id`. `transactions` is unchanged and gets no grouping column. `tx_id` is deprecated and dropped later | Roles 2, 3 | |
| Contribution uniqueness: R2-06 built a partial unique index (rows not `failed`) instead of the planned UNIQUE (`cycle_id`, `round`, `member_id`), so a member can retry after a failed send. Approve? | **Resolved (2026-10-25, confirmed by Role 2):** the partial unique index `uq_stokvel_contributions_once`: one contribution per (cycle, round, member) that has not `failed`, so a member cannot pay a round twice but can retry one whose attempt failed | Roles 2, 3 | |
| How do members see their stokvel's payouts? A stokvel's payout quote has no `sender_user_id`, so row-level security on `quotes`, `remittances` and `transactions` hides it from them | **Resolved (2026-10-25, confirmed by Role 2):** another way than the proposal below. `GET /stokvels/{id}` (R2-14, #236) reads each round's payout from `stokvel_payouts` (release status and hash, remittance status and ID), which members can already read, so the `quotes`, `remittances` and `transactions` policies were not changed for payouts. Pool release and contribution legs on the `STOKVEL` account are readable through the two R2-11 policies (`V20261016_1500`). Former members: see the next row | Roles 2, 3 | 0004 |
| What do former members see? `stokvel_is_member` counts former members, so under that proposal someone who left would still see later rounds' payouts. Intended, or only rounds from while they were a member? | **Decided (product, Sian, 2026-10-25):** a former member sees the stokvel's activity up to the time they left (`stokvel_members.left_at`), and nothing after it. **Not built yet:** today `GET /stokvels` and `GET /stokvels/{id}` show a stokvel to current members only (`left_at IS NULL`), so a former member sees nothing at all, while row-level security (`stokvel_is_member`, `stokvel_account_is_member`) would let them read everything, including later rounds. Nothing sets `left_at` yet; build this with leaving a stokvel (#237): bound the member read rules and the detail view by `left_at` | Product, Roles 2, 3 | |
| What sender name does a payout's recipient see? The recipient is usually not a member, so row-level security hides the stokvel and they see no sender name. Options: the stokvel's name (needs a narrow lookup that skips row-level security, such as a `SECURITY DEFINER` function), a fixed label such as "Stokvel payout", or nothing | **Decided (product, Sian, 2026-10-27): the stokvel's name, for every recipient.** `stokvel_payout_name(stokvel)` (`V20261027_1847`, `SECURITY DEFINER`) returns the name and nothing else, and only to a customer the stokvel has paid (or on a worker or admin route). The transfers list and page, the dashboard's in-flight list and account history put it in `counterparty_name`; a payout's account history lines (the payout to the fiat account and the incoming leg on the settlement wallet) read "Stokvel payout from {name}". Without a name they keep the labels for any received transfer: "Payout" on the fiat account, "Received from a sender" on the settlement wallet | Product, Roles 2, 3, 4 | |
| When are the fee and margin taken? **A:** the payout's single remittance fee is split equally across the members and paid on top of each contribution, so the beneficiary gets the full pool. **B:** taken from the pool at payout, so members pay exactly the contribution and the beneficiary gets the pool minus fees. | **Resolved (2026-10-16): A, fee on top.** Built in R2-11 (`contribution_fee_share`, the contribution's `fee` leg). D6 and CONTEXT.md updated. R3-05 (#242) pays the full pool and must not charge the fee again | Product | #233 |
| Are the fee and margin taken from the pool converted back to fiat, and if so how? Suggestion: convert them to fiat at finalisation and deduct them from the pool before the payout, so beneficiaries receive their payout in fiat after fees | **Resolved (2026-10-16):** moot under fee on top. The fee is collected in fiat from each member's account (the `fee` leg, to RemitX fee revenue), so nothing is taken from the pool | Product | #233 |
| Fee shares priced at each member's own rate (D6) can differ within a round, in a stokvel whose currency is not ZAR, and need not add up to the fee on the pool paid out. Accept for the prototype, or lock the round's rate at its first contribution? | Open. Until decided, R3-05 pays the full pool and does not reconcile the fee against the shares | Product, Role 3 | #340 |
| A contribution left `pending` (its enqueue was lost) or `processing` (no receipt after the retries, or a worker stopped between claim and signing) is only logged (`event=stokvel.contribution_unconfirmed`, `contribution_unsigned`). Extend `reclaim_stuck_settlements` to re-queue pending contributions, or leave them to the event sync (R2-13, #235), which can confirm one from its `ContributionMade` event? | **Partly answered (#235):** the event sync now confirms any contribution that was mined, from its `ContributionMade`, whatever its status said. Still open: one that was never sent (`pending` after a lost enqueue, or `processing` unsigned) is only logged; re-queueing it from `reclaim_stuck_settlements` is the remaining option | Roles 2, 3 | #234, #235 |
| **Who records a release (OI-1)?** Proposal from R2-13 (#235): `stokvel.release_pool(cycle_id, round, tx_hash=None, block_number=None)` is the only writer of a release. It creates the payout row if missing; if the round is already released on-chain (a `RoundFinalised` with its hash, or `getCycle`'s `nextToFinalise` past it) it only records it, otherwise it calls `finalise` and treats `AlreadyFinalised` as done; then books `STOKVEL` → Treasury and triggers `settle_payout`. The event sync queues it with the event's hash and block; the scheduled release (#248) and the admin (#247) without | **Resolved (2026-10-25, confirmed by Role 2):** the shared guard `stokvel_ledger.record_pool_release`, as built in R3-04 (#241), not a single task. It is the only writer of a release, in the caller's transaction: it creates the payout row if missing, moves it to `released` only from `pending`/`processing`, and books `STOKVEL` → Treasury. The event sync calls it inline from `RoundFinalised` (so `CycleClosed` closes the cycle in the same run); `stokvel.release_pool(cycle_id, round)` only sends `finalise` (for #248, #247) and records from its receipt, and on `AlreadyFinalised` leaves the event sync to record it. The hash always comes from an event or a receipt, so `stokvel_payouts_released_on_chain` always holds. The payout is queued separately, by `queue_released_payouts` at the end of each sync run | Roles 2, 3 | #235, #241 |
| Should a round open for payments only on its start date? Today a round opens as soon as the round before it is fully paid (the contract's `openRound`), and neither the contract nor the API checks `stokvel_rounds.start_time`, so members can pay ahead of the schedule. Paying ahead is one reason a round can need `finalise` later (R3-04): its next round fills before its payout time, so no later contribution releases it. If wanted, `POST /stokvels/{id}/contributions` would refuse a payment before the open round's `start_time`, with no contract change. The next round must still open once the round before it is fully paid, not once it is released: D5 releases a round only once the next round is fully paid, so waiting for the release would deadlock | Open (2026-10-19): product decision; would be built in R2-11 (#233) | Product, Roles 2, 3 | #241 |
| Contribution deadline informational only, with no penalties on the platform (D7)? | **Resolved (2026-10-25):** yes, as built. The contract accepts late contributions (`roundDeadlines` is informational) and the API never checks the deadline | Product | |
| Stokvel has no sending limits, but each contribution counts toward the member's own limits (D8)? | **Resolved (2026-10-25):** yes, as built. `POST /stokvels/{id}/contributions` checks the member's limits on the contribution plus its fee share, in rand, as a remittance counts its gross amount | Product | |
| Treasury key storage: the encrypted key sits in `.env` rather than a database column (as the wallet seed does today). Acceptable? | **Resolved (2026-10-25):** yes, as built (#277): `EVM_TREASURY_KEY_ENCRYPTED`, Fernet-encrypted with the separate `EVM_ENCRYPTION_KEY`, decrypted only by the worker. The vault admin key is stored the same way (#244) | Product | |
| Approve P5 (manual admin finalise fallback)? | **Resolved (product, Sian, 2026-10-19: keep an admin Release payout button as a fallback).** Frontend R4-11 #260, backend R3-10 #247 | Product | |
| Merge the contribution deadline and payout time into one date per round (P6)? | Open: both kept for now, as the contract, `stokvel_rounds` and the frontend have both (2026-10-16). Merging needs no contract change: the backend can send the same date as both | Product | |
| Stuck round if a member never pays: accept it, relying on cancellation (P4) as the exit? | Open | Product | |
| Should an admin's look at a stokvel's member data (for oversight) also be logged, as KYC reads are? | Open | Product, Role 5 | |
| PR #211's log redaction also hides EVM transaction hashes in logs (they look like keys) until exact-value redaction lands in #204. Acceptable for debugging and the demo? | **Resolved (2026-10-25):** moot. The log redaction was removed after review on #211, so transaction hashes are logged in full | Role 2, Role 6 | |
| Demo timing: payout times a few minutes apart, and how to show a stuck round | **Resolved (2026-10-25, R4-14 #370):** the setup's "Every 5 minutes (demo)" frequency. The last round still needs a `finalise` after its payout time: the scheduled release (R3-11 #248) sends it within a minute, and R3-10 #247 stays as the fallback | Role 6 | |
| Legal status of P2 (payout conditional on the next contribution) | Open | Product | |
| A payout left `processing` with no stored hash (a worker stopped after `release_pool`'s claim, before signing) is never retried: `release_pool` and the scheduled release both leave it, and the scheduled release logs `stokvel.release_sweep_stuck` each run once it has been held `STOKVEL_RELEASE_STUCK_LOG_SECONDS`. Hand stale claims back to `pending` automatically, as the settlement reclaim does? | Open (R3-11 #248 left it for a person) | Role 3 | |
| Remittance status names: brief's `created → burning → burnt → credited` vs existing ledger states. Recommendation: keep the ledger states (fewer changes) | **Resolved (product, Sian, 2026-10-25):** keep the existing ledger states, as built. A stokvel's payout settles through the same legs and statuses as any remittance (`pending`, `processing`, `confirmed`, `failed`), not the brief's `created → burning → burnt → credited`. Listed under Deviations from the brief | Product, Roles 2, 3 | |
| Payout destination (#293): pay the pool to the scheduled member's chosen beneficiary, or into the member's own account? | **Resolved (2026-10-14):** the stokvel pays the member's chosen beneficiary directly, as a remittance with the stokvel as sender. Stored per cycle in `stokvel_cycle_members.payout_beneficiary_id` and `payout_currency` | Product, Roles 2, 3 | |
| Row-level security for the new stokvel tables | **Resolved (2026-10-09):** section 3, "Row-level security"; R2-05 and R2-06 reuse the same functions | Roles 2, 3 | |
| Round schedule: is it sent with `POST /stokvels` (section 12, step 1: start time, deadlines and payout time per round) or when the Organiser starts a cycle (R2-10)? `stokvel_rounds` hangs off a cycle; R2-09 now opens cycle 1 as `forming` at creation, so the schedule can be written to it either way. Neither R2-07 nor R2-09 takes a schedule | **Resolved (2026-10-19, R2-10 #232):** sent when the Organiser starts the cycle (`POST /stokvels/{id}/cycles`, section 5), one round per member in payout order: the order it pairs with is only final then, and each cycle gets its own schedule. The create wizard (#252) no longer collects it; the setup page (#255) will. Product to confirm | Product, Roles 2, 3 | #232 |
| Contribution entered in fiat at creation: the API stores UCTUSD (D13). The wizard (#252) lets the Organiser type the Stokvel currency and converts with the quote preview's `fiat_to_token_exchange_rate`, rounded to the cent, so no API change is needed | **Resolved (Role 4, 2026-10-19):** decided as described | Role 4 | |
| Opening the next cycle: R2-09 opens only cycle 1 (at creation, or on demand for a stokvel made before that). After a cycle closes, both setup routes answer 409 `cycle_not_forming` until a new `forming` cycle exists, with rows for the members who continue | **Resolved (2026-10-25, R2-15 #237):** the worker opens it when it records `CycleClosed`, in the same transaction, with rows for the Organiser and anyone who joined during the cycle; members of the closed cycle get one by continuing (section 5). Undecided members are treated as leaving when the next cycle starts. The Organiser's first setup or continuation call opens it for a cycle that closed before this | Roles 2, 3 | #237 |
| Closing a stokvel: the Organiser cannot leave after a cycle (R2-15); getting out means closing the stokvel for everyone. No route sets `deactivated_at` yet. It would also settle the question above on pending invitations when a stokvel is deactivated | Open (2026-10-25): follow-up to #237 | Product, Roles 2, 3 | |
| Stokvels created before R2-09 have no cycle. No backfill migration: the Organiser's first payout-order or beneficiary call opens cycle 1. A member who is not the Organiser cannot (row-level security lets only the Organiser insert a cycle) and gets 409 `cycle_not_forming`. Acceptable, or backfill in a migration? | **Resolved (2026-10-25, confirmed by Role 2):** no backfill migration. The Organiser's first payout-order or beneficiary call opens cycle 1; another member gets 409 `cycle_not_forming` until then | Roles 2, 3 | |
| The payout order takes `member_id`s (`stokvel_members.id`), but no route returns them yet. The frontend needs them from `GET /stokvels/{id}` (#236) before the Organiser's order screen can work | **Resolved (2026-10-19, #236):** `GET /stokvels/{id}` returns `members[].member_id` and `cycle.payout_order` | Roles 2, 4 | |
| Starting a cycle (R2-10, #232) must lock only current members' rows. A former member's row stays in the cycle, unlocked and, after the next payout order, with no position; `stokvel_cycle_members_locked_is_complete` allows that. It must also check that the current members' positions are exactly `0..n-1` (`{row.payout_position for current rows} == set(range(n))`), not only that each current row has one: a member who leaves after the order is set keeps their position until the next `PUT /payout-order`, leaving a gap (round 1 could pay nobody), and an invitee who accepts while `forming` has no position. R2-10 should also take the `stokvels` row lock, so a setup call or an accept cannot interleave with the start | **Resolved (2026-10-19, R2-10 #232):** all three are built and tested. The cycle's members are its locked rows, so R2-11's round counting and fee share now use only locked rows (a former member's unlocked row had made round 0 impossible to fill) | Roles 2, 3 | #232 |
| A started cycle whose on-chain registration fails for good (a refusal the API should have prevented, a reverted `startCycle`, the contract and the database disagreeing, or no receipt after the retries) stays `active` with no `registered_at`: contributions answer `cycle_starting` until a person fixes it, and nothing rolls it back to `forming` (the pending invitations it lapsed stay lapsed). Logged as `event=stokvel.cycle_start_refused` / `cycle_start_reverted` / `cycle_start_needs_person` / `cycle_start_unconfirmed`, and again by each `stokvel.register_started_cycles` run, which re-queues it (#348 review), so a fix on the chain side is picked up without a person. Still open: a rollback route for a cycle that can never start? | Open (2026-10-19, #232) | Roles 2, 3 | |
| The payout currency is copied onto the member's cycle row when they choose a beneficiary (R2-09). If the beneficiary's own payout currency is edited later, or the recipient closes that account, the stokvel still holds the copied currency. R3-05 (#242) should re-check at payout that the recipient still holds an account in the row's `payout_currency`, and decide what happens if not (fail the round's payout, or fall back) | **Resolved (2026-10-25, confirmed by Role 2):** fail, no fallback, as built in R3-05 (#242). `settle_payout` re-checks that the beneficiary still exists, still pays out in the row's `payout_currency`, and that its user holds UCTUSD and payout-currency accounts. If not, the payout's `remittance_status` becomes `failed` with nothing created, and `event=stokvel.payout_needs_a_person` is logged. The pool stays in the Treasury Wallet. How a person then resolves it is a separate open question below | Roles 2, 3 | |
| How does a person resolve a payout that `settle_payout` marked `failed` (beneficiary no longer fits)? Nothing moves it back to `pending` today, so the pool sits in the Treasury Wallet. Options: an Administrator action (with R3-10, #247) that resets it once the member has chosen a new beneficiary, or a manual database fix for the prototype | Open (2026-10-20, #242) | Roles 2, 3 | |
| How is a payout re-attempted once its burn failed (rejected or reverted, R3-06)? Its legs are `failed`, no balance moved and the pool is still in the Treasury Wallet, but nothing re-settles a failed group, for a user's remittance or a payout, and the payout's `quote_id` and `remittance_id` are unique, so a second attempt needs a new quote and remittance in their place (or a history of attempts). Options: an Administrator action (with R3-10, #247) that creates a fresh remittance from the released pool, or a manual fix for the prototype. The release is never repeated either way | Open (2026-10-21, #243) | Roles 2, 3 | |
| Stokvel list fields from the frontend mocks (#251, #252): `phase`, `current_round`, `total_rounds`, `next_payout_time` need the cycle tables (#227), `my_contribution_status` the contribution table (#228). Both have now landed; add them to `GET /stokvels` in a follow-up to R2-07? | **Resolved (product, Sian, 2026-10-25):** not needed. The four fields are on `GET /stokvels/{id}` (#236); `GET /stokvels` stays as it is, and the list screen (R4-09, #258) shows name, contribution amount and member count, so a member opens a stokvel to see its round and payout | Roles 2, 4 | |
| A customer can insert their own `stokvel_members` row for any stokvel: the write rule is `user_id` = the caller (R2-04), with no check for an accepted invitation. No route does it today; R2-08 (accepting an invitation) relies on the API. Tighten the policy, or accept it as API-enforced? | **Resolved (2026-10-17, R2-08):** tightened. One policy per operation, no `DELETE`; insert only as the Organiser with no invitation or with your accepted invitation to that stokvel; identity columns fixed by a trigger. `stokvel_invitations` tightened the same way, since a customer could otherwise forge the accepted invitation (section 3) | Roles 2, 3 | #230 |
| When a stokvel is deactivated, should its pending invitations be set to `lapsed` (or `revoked`)? R2-08 hides them from `GET /stokvels` and refuses to accept them, but leaves them `pending`, because no deactivation route exists yet. Since R2-16 (#297) the Organiser can revoke them by hand | Open (2026-10-17): for the ticket that adds deactivation | Roles 2, 3 | |
| Seeder and load test: update stories and `tools/loadtest/fake_xrpl_worker.py` for EVM | **Resolved (2026-10-15, #278 and R6-02 #267):** both fake the EVM burn and receipt; the load test's fake worker is now `fake_evm_worker.py`. Still to do: recalibrate the load test's burn timings (`qa_burn_timings.sql`) once QA has real EVM burns; until then the profiles say `"calibrated_on": "XRP Ledger, pre-EVM"` and every report shows it | Role 6 | |
| The ledger treasury (`REMITX_EVM_WALLET` account) still starts from the XRPL wallet's balance (`V20260924_1352` read the XRPL trust line), so it does not match the EVM Treasury Wallet's UCTUSD. Rebase it with a one-off `treasury_funding` adjustment to the EVM balance? Until then `verify --chain` reports `(differ)` and says why (#267 review) | Open (2026-10-17): ticket to open | Roles 2, 3, 6 | |
| #299 asks for every invitation with its status (`pending`, `accepted`, `declined`, `revoked`, `lapsed`) for members (product decision, 2026-10-09). `GET /stokvels/{id}` returns pending invitations only (`list_pending_for_stokvel`). Return all of them there (the frontend already shows the status), or is pending-only enough for the MVP? | Resolved (R2-17, #375): `GET /stokvels/{id}` returns every invitation, of any status (`list_for_stokvel`); `account_reference` stays Organiser-only | Roles 2, 4, Product | |

Resolved: finalisation is automatic (D5); a manual admin finalise is kept as a fallback, approved by product on 2026-10-19 (P5).

Resolved (2026-10-08): the Treasury approves the stokvel contract once per contract address (`approve(vault, max)`), and the worker checks the allowance before each `contribute` (section 1, "Treasury allowance"). Backend confirmed sections 1 and 6.

### Member visibility of stokvel payouts (superseded)

_Status: superseded 2026-10-25. R2-14 (#236) shows members their payouts from `stokvel_payouts` instead, so the `quotes` and `remittances` policy change below was not built; the `transactions` policies for `STOKVEL` account legs were (R2-11). Kept for the record. ADR 0004._

**Problem:** a stokvel's payout quote has no `sender_user_id`, so row-level security hides the quote, the remittance and their transactions from the stokvel's members. Their account history shows no counterparty.

**Proposal:**
- Keep `sender_user_id` NULL on a stokvel's quote.
- In the `quotes`, `remittances` and `transactions` policies, add `OR (stokvel_id IS NOT NULL AND stokvel_is_member(stokvel_id))` to the party check.
- On `transactions`, also let members see legs on the stokvel's `STOKVEL` account. Pool release and contribution legs have no quote, so the clause above does not reach them. **Built in R2-11 (#233), revised after review:** `transactions_by_current_user` is unchanged. Two permissive policies sit beside it (`V20261016_1500`): `transactions_stokvel_member_select` lets a current or former member read legs on their stokvel's `STOKVEL` account (`stokvel_account_is_member`), and `transactions_stokvel_member_insert` lets a current member record only a contribution's token leg: type `stokvel_contribution`, from the Treasury Wallet (`account_is_treasury_wallet`) into their stokvel's account (`stokvel_account_is_active_member`). Both sides are pinned. Pool release legs (`STOKVEL` → Treasury) are recorded by the worker, which the original policy already allows. There is no update or delete policy for these legs, so no member's session can change or remove one, as the stokvel tables allow no deletes. Without the insert policy the contribution API could not record its token leg (Treasury → `STOKVEL`) under row-level security. **Needs Roles 2 and 3 approval** (Sian and Mridula, in #340).
- Members then see payouts in the stokvel's history (`GET /stokvels/{id}`).

**Rejected:**
- Setting `sender_user_id` to the scheduled member. The pool would count against that member's limits (against D8), and "sender" would mean two things.
- A server-side read that skips row-level security. The access check would then live only in application code.

**Notes:**
- #293 is decided: the pool goes to the member's chosen beneficiary, not their own account, so every member (including the one paid) needs this change to see the payout.
- The recipient already sees the payout (section 3, "Stokvel as quote sender").

---

## 9. Implementation progress

Milestones (Katlego-Sekoele/RemitX): *EVM wallet setup and switch over*, *Bank API Integration and Bank Deposit simulation switch over*, *Smart Contract Creation and Connection*.

| Step | Status | Issues | Notes |
|---|---|---|---|
| Replace the XRPL layer with EVM | In progress | #276 (was #204) | See "EVM switch-over" below. Merged: the worker-only key loader and the `web3` dependency (PR #211), and the send and receipt helpers (PR #290). In progress: the burn (#278). XRPL code stays in place (D11) |
| Treasury Wallet as EVM address, encrypted key | Done | #277 (was #205) | PR #211: wallet creation script, worker-only key loader, extended gitleaks rule and leak tests (its log redaction was removed in review). Operator role granted at deployment (#218), funded (#224), address in section 2 |
| Burn UCTUSD on EVM | In review | #278 (was #206) | Settlement calls `burn(uint256)` from the Treasury through `evm_service.burn_tokens`; the hash is stored before the send; a retry waits on the stored hash; Treasury sends are serialised by `treasury_send_lock`. Seeder and load-test fakes updated. Burn method confirmed by a 1-base-unit test burn on 2026-10-14 (section 8) |
| Contract: stokvels and cycles, interface (DEC-1) | Done | #197, #212, #215 | Merged in PR #282 (2026-10-08); #279–#281 closed as superseded. Matches section 1 and D12 |
| Contract: contributions and finalisation | Done | #198, #212 | Merged in PR #282: payout-time gate (D12), external `finalise` |
| Contract: pause and resume | Done | #217 (was #199) | Merged in PR #282 (contract only; backend route is R3-07 #244, admin control R4-07 #256) |
| Contract tests | Done | #216 (was #200) | 73 in total: hand-written tests for every rule plus randomised invariant tests (80 runs × 60 steps against a reference model), from #282 and #291. With #285: 73 tests, 100% lines and 99% branches (coverage fixes and the ABI drift test) |
| Contract testnet deployment | Deployed (smoke test pending) | #218 | Deployed 2026-10-09 at `0x2f24…8Fe1` (section 2) from the fixed contract (#291); all post-deploy checks passed; verified on Sourcify. Record and `.env.example` merged in #284. Closes when a `contribute` from the Treasury Wallet succeeds on testnet (Role 2 holds the key; needs `createStokvel`, `startCycle`, `approve`, `contribute`) |
| Contract README, ABI export, ADR | Done | #219 | PR #285: `contracts/README.md`, `contracts/abi/StokvelVault.json` (the ABI the backend loads), `docs/adr/0002-one-contract-many-stokvels.md` |
| Contract member cap (DEC-3) | Contract side done | #213 | `maxMembers` = 3 at deployment. Backend `MAX_STOKVEL_MEMBERS` and ticket wording remain |
| Contract cancel and refund | Not in v1 | #220 | P4 |
| Backend connection to the contract | Not started | #273 (was #201) | |
| Members create stokvels and invite others | In progress | #229 (was #209), #230, #297, #375 | Create and list done (#229, PR #339); invite, accept and decline done (#230, PR #344); revoke done (#297); every invitation, of any status, on `GET /stokvels/{id}` (#375) |
| Payout order and beneficiary | Done | #231 | `PUT /stokvels/{id}/payout-order`, `PUT /stokvels/{id}/members/me/beneficiary`; cycle 1 opens at creation (PR #347) |
| Start a cycle | In review | #232 | `POST /stokvels/{id}/cycles` with the round schedule; `stokvel.start_cycle` registers it on-chain (`createStokvel`, `startCycle`) and records it, `stokvel.register_started_cycles` re-queues any left unregistered; contributions wait for it (`cycle_starting`) |
| Continue or leave after a cycle | In review | #237 | `POST /stokvels/{id}/members/me/continuation`; the worker opens the next cycle on `CycleClosed`; the Organiser starts it with the members who continued (section 5) |
| DB models and migrations | In progress | #226, #227, #228, #238, #239, #240, #232 | Section 3. Done: group tables with row-level security (#226, PR #300); ledger account, transaction types, stokvel quote sender and EVM names (#238, #239, PR #301); cycle tables with row-level security (#227, PR #306); contribution table (#228, PR #338); payout table (#240, PR #342). In review: cycle on-chain registration columns (#232) |
| Worker tasks | In progress | #234, #235, #232, #241, #242, #243, #248 | Section 4. Built: `stokvel.submit_contribution`, `stokvel.confirm_contribution` (#234), `stokvel.sync_events` (#235). In review: `stokvel.start_cycle`, `stokvel.register_started_cycles` (#232); `stokvel.release_pool` and release recording (#241); `stokvel.settle_payout`, the payout remittance (#242); payout settlement through the existing burn chain (#243). In review: scheduled release, `stokvel.release_due_rounds` (#248) |
| API routes | In progress | #229, #230, #231, #233, #236, #297, #247 | Section 5. Built: `POST /stokvels`, `GET /stokvels` (#229); `GET /stokvels/{id}` (#236); `POST /stokvels/{id}/cycles` (#232); `POST /stokvels/{id}/contributions` (#233); invitations (#230); revoking an invitation (#297); payout order and beneficiary (#231, PR #347); `POST /admin/stokvels/{id}/rounds/{n}/finalise` (#247) |
| Stokvel audit log (admin actions) | Done | #249, #244, #247 | Section 5. Actions and subjects on the existing audit log. Pause (R3-07) and manual finalise (R3-10) call `record_audit` |
| Frontend screens | In progress | #251, #258 | Routes and nav (#251). Member and admin stokvel screens call the API (#258, admin reads wired 2026-10-27) |
| TrustMeBank deposits and withdrawals | Not started | #274, #275 (were #202, #203) | Required in this build (optional in the brief) |
| Stokvel cancellation | Not in v1 | #208 | P4 |
| Seeder and load test for EVM | Done | #267 (R6-02) | Builds on #278 |
| Cloud EVM and contract settings | Done | #263 (R5-02) | GCP API and worker get the testnet contract address, member cap and sync start block. Vault admin key is a worker-only secret. XRPL settings stay (D11). Legacy Render was not changed |
| Stokvel demo data | Done | #268 (R6-03) | The seeder's `demo` scenario: three verified, funded members in a stokvel ready to start, and a second with an invitation pending (section 13). Merged in PR #358 |
| End-to-end: three members, three rounds | In progress | #269 (R6-04) | Built: `api/tests/test_stokvel_three_rounds.py`, the brief's scenario through the API and the worker's own tasks, with only the chain faked; runs in CI. Still to do: the same run against the deployed version |
| End-to-end: blocked round, duplicate and early finalisation | In progress | #270 (R6-05) | Built: `api/tests/test_stokvel_blocked_duplicate_early.py`, each case refused through the API and the worker on the R6-04 setup, and each way out (the last payment, the payout time passing). Still to do: the live demo script, with R6-07 (#272) |
| Pool reconciliation | Built | #245 | One burn leg per quote. A burn with no quote is not rejected: old rows may have none. `check_pool_reconciliation` tested on a ledger of three rounds. A `processing` burn with a hash is `in_flight`, not part of the float. `api/scripts/check_pool_reconciliation.py` reads the chain and prints that figure. Not run on the seeded demo: that scenario leaves the cycle forming, and an unrebased ledger still starts from the XRPL balance (section 8), so the command fails until that rebase. No rate-difference leg (D13, #298 closed) |

### Brief timeline

| Date | Target |
|---|---|
| Fri 9 Oct | Contract deployed and tested; backend can submit a contribution and read state |
| Fri 16 Oct | One full round end to end; member and admin screens |
| Fri 23 Oct | All three rounds on the deployed version, plus blocked round and rejected duplicate and early finalisation; settlement retry test passes; code freeze and tag |
| Mon 26 – Wed 28 Oct | Rehearsal, backup video, submission, presentation |

### Work breakdown

1. **EVM switch-over** (#204–#206): see the list below.
2. **Contract** (#197–#200, now #212–#220): Hardhat project in `contracts/` (done, PR #282), tests per brief §7.5 (done), deploy and record the address in section 2 (#218, in progress).
3. **Backend stokvel domain**: models and migrations → repositories → controllers → thin routes. Copy the shape of `confirm_remittance` for contributions: lock the user, check standing and limits, check available balance, insert pending legs. **Built (R2-11, #233):** the contribution row points at its legs (`fiat_tx_id`, `token_tx_id`, `fee_tx_id`) instead of a group id (section 8).
4. **Settlement** (#201): contribution submit and confirm, event sync, pool release (`STOKVEL` → Treasury) → payout remittance from the Treasury Wallet, with the stokvel as the quote's sender → existing burn chain. A retried settlement must not duplicate release, burn or credit.
5. **Frontend**: member and Organiser screens, invitations, admin pause and cancel, using shadcn/ui and Aceternity per CLAUDE.md; run `npm run generate:api`.
6. **Testing and demo**: three members × three rounds, blocked round, duplicate contribution, early finalisation, settlement retry test, seeder story updates.

### EVM switch-over: what changes

| Area | Change |
|---|---|
| `api/remitx_worker/xrpl_service.py` | Keep it, with a comment saying it is no longer used (D11). The worker stops calling it and calls the new `evm_service.py` (web3.py) instead, which loads and decrypts the Treasury key, sends transactions, waits for them to confirm, and does the burn |
| `platform_wallet/scripts/create_xprl_platform_wallet.py` | Keep it, with a comment saying it is no longer used (D11). The EVM wallet is made by `create_evm_platform_wallet.py`, which generates an EVM key and saves it encrypted in `.env`. It needs no faucet wallet or trust line |
| `api/pyproject.toml` | Add `web3` and keep `xrpl-py` (D11). An old database migration still imports `xrpl-py`, so removing it would break `alembic upgrade head` |
| `config.py`, `.env.example`, `.env.minimal.example` | New `EVM_*` variables (section 2). Keep `XRPL_*`, `PLATFORM_WALLET_*` and `UCTUSD_ISSUER*` in place, marked decommissioned and unused by EVM code; do not remove them |
| Migration | Done in R3-01 and R3-02 (#238, #239): `xrpl_tx_hash` → `evm_tx_hash` (old column dropped later), the `REMITX_XRPL_WALLET` type and CHECK, the seeded wallet label, `STOKVEL` and the new transaction types |
| `services/transfer_timeline.py`, `controllers/remittance_controller.py`, settlement-recovery code | Replace "Settling on XRPL Testnet / RLUSD" text (the `xrpl_tx_hash` field is now `evm_tx_hash`, #239) |
| `remitx_worker/tasks.py` | Burn and confirm tasks keep their shape; call `evm_service` |
| Tests | Worker burn tests mock `xrpl_service`: repoint at `evm_service` |
| `tools/seeder`, `tools/loadtest/fake_xrpl_worker.py` | Done (#278, R6-02 #267): the seeder and the load test fake the EVM burn; the fake worker is now `tools/loadtest/fake_evm_worker.py`, and `verify --chain` reads the Treasury Wallet's UCTUSD balance |
| Docs | [CLAUDE.md](../CLAUDE.md) (hard constraint says "XRPL Testnet only"; RLUSD wording), [DEPLOYMENT.md](DEPLOYMENT.md), `project-brief.md` (not [Transaction_Flow_Context.md](Transaction_Flow_Context.md), which stays unchanged as the original project's record); add ADRs for single contract with many stokvels (done: `docs/adr/0002-one-contract-many-stokvels.md`, #285), the `STOKVEL` ledger account (done: `docs/adr/0004-stokvel-ledger-account.md`, #238), and the single Treasury Wallet; add "Cancellation" to CONTEXT.md if P4 is approved |

## 10. Features added

_Add one entry per feature as it lands: what it does, who owns it, PR link._

| Feature | What it does | Owner | PR |
|---|---|---|---|
| Stokvel contract (`StokvelVault`) | One contract for every stokvel: create stokvels, start cycles (members, schedule), contributions filled in order, automatic release and `finalise` under D5 and D12, admin pause and resume, member cap set at deployment. 69 tests | Kerry (Role 1) | #282 (merged) |
| Contract deploy script | `npm run deploy:testnet`: deploys with admin = deployer, operator and release target = Treasury Wallet, UCTUSD, `maxMembers` 3; checks settings, token, gas and roles; records the deployment | Kerry (Role 1) | #284 |
| Contract ABI for the backend | `contracts/abi/StokvelVault.json`, regenerated by `npm run export:abi`; a test fails if it drifts from the contract | Kerry (Role 1) | #285 |
| Create and list stokvels | `POST /stokvels`: a KYC-verified user creates a stokvel and becomes its Organiser and first Member, with its `STOKVEL` ledger account, in one transaction. `GET /stokvels`: the caller's current stokvels and pending invitations | Claire (Role 2) | #229 |
| Stokvel invitations | The Organiser invites a verified user by account reference in the Stokvel currency; the invitee accepts (becoming a Member, within `MAX_STOKVEL_MEMBERS`) or declines; the Organiser may revoke it while it is pending. Nobody becomes a Member without accepting, enforced by the API and by row-level security | Claire (Role 2) | #230, #297 |
| Payout order and beneficiary | Before a cycle starts, the Organiser enters the payout order the members agreed (every current member once) and each member chooses which of their beneficiaries the stokvel pays their pool to, in that beneficiary's payout currency. Both can change until the cycle starts, then are locked. A new stokvel opens its first cycle as `forming`, and members who accept join it | Claire (Role 2) | #231 |
| Continue or leave after a cycle | When a cycle closes, the next opens as `forming`. Each member continues (keeping or changing their beneficiary) or leaves; the Organiser always continues. The Organiser sets the order and starts it with those who continued; anyone who never chose leaves at the start | Claire (Role 2) | #237 |
| Member stokvel screens on the API | List, detail, invite, accept, decline, beneficiary, payout order, start cycle and contribute go through the generated client. Detail is `GET /stokvels/{id}`. The list, a stokvel page and the admin rounds page refetch while open | Karabo (Role 4) | #258 |
| Stokvel audit actions | `AuditAction` and `AuditSubject` can record a contract pause, a resume and a manual finalise. List them with `subject_type`. Pause and manual finalise both call `record_audit` | Katlego (Role 3) | #249, #244, #247 |
| Manual round release | `POST /admin/stokvels/{id}/rounds/{n}/finalise`: an administrator queues `finalise` for one ready round when the automatic release has not. The contract still refuses a round that is not ready, and a round is released and credited once | Katlego (Role 3) | #247 |
| Cloud EVM settings | QA and production Cloud Run get `STOKVEL_CONTRACT_ADDRESS`, `MAX_STOKVEL_MEMBERS` and `STOKVEL_SYNC_START_BLOCK` from Terraform (testnet defaults). The vault admin key is a worker-only secret. XRPL variables stay deployed, unused | Katlego (Role 3) | #263 |
| Pool reconciliation | Proves a round is burned once, for the pool only, and that the Treasury's on-chain UCTUSD equals the confirmed ledger float. Tokens still in the contract are a separate figure | Katlego (Role 3) | #245 |

## 11. How things are connected

```
Frontend → API route → controller → ledger legs (pending) → queue
       → worker (web3.py) → stokvel contract → event → sync task → database
```

- **Contribution:** the member's fiat account is debited for `contribution_amount × live rate` plus their fee share (D6), and both count toward their limits (D8). The ledger books member fiat → RemitX bank, Treasury → `STOKVEL` and member → fee revenue (section 3). The worker sends exactly `contribution_amount` UCTUSD from the Treasury Wallet to the contract with `contribute`. The contribution is `confirmed` only after the on-chain event.
- **Finalisation:** when every member has paid round N+1 (or everyone has paid the last round) **and the round's payout time has passed**, the contract releases round N's pool to the Treasury Wallet. The worker books the `stokvel_pool_release` leg `STOKVEL` → Treasury Wallet (section 3) through `stokvel_ledger.record_pool_release`: from the `RoundFinalised` event, or from `release_pool`'s receipt for a round it released with `finalise`, so the `STOKVEL` balance falls by the pool and keeps equalling the stokvel's unreleased pools in the contract.
- **Payout:** the stokvel is the quote's sender, but the pool is paid from the Treasury Wallet, where the release has already put it. A quote and remittance are created to the scheduled member's Payout beneficiary by `stokvel.settle_payout` (R3-05), which the event sync queues once the release is recorded, for the full pool: FSE's fee and margin were already paid by the members on top of their contributions (D6), so the payout charges none. `settle_payout` hands it to the existing settlement chain (R3-06), which burns the UCTUSD and credits the beneficiary's payout-currency account. The burn hash, beneficiary credit and remittance reference are stored together: the payout row holds the burn hash and remittance reference, and its `quote_id` leads to the credit leg.
- **No bridge:** nothing moves on the XRP Ledger; the remittance step produces the quotation, record and reference, and the burn stands for the simulated cash-out.

## 12. User flow

1. A KYC-approved user creates a stokvel (name, Stokvel currency, contribution, start time, deadlines and a payout time per round).
2. The Organiser invites users by account reference. Only KYC-approved users with a fiat account in the Stokvel currency can be invited. Nobody is a member until they accept.
3. The members agree the payout order among themselves, off the platform. The Organiser enters it from the invite list (people who have not accepted yet can already be placed), and every member can see it (D3). Reordering is saved shortly after the Organiser stops dragging, not on every move.
4. Each member chooses a Payout beneficiary and payout currency (the account must already exist). The Organiser does this on the setup screen, from the same beneficiary picker used when sending money.
5. The Organiser walks a stepper: people, payout order, schedule, then start. Start stays closed until at least two people are in and everyone on the invite list has accepted. The screen does not start while an invitation is still pending, so those invitations are not lapsed from the screen. Membership, order and beneficiaries lock when the cycle starts.
6. Each round, every member contributes before the deadline (informational only).
7. The contract finalises automatically once the round is fully paid and its payout time has passed (a scheduled task releases it if everyone paid early). An administrator can release that same round by hand if the automatic release has not (`POST /admin/stokvels/{id}/rounds/{n}/finalise`, P5). The payout remittance goes to the scheduled member's beneficiary; the member sees status, hashes and the remittance reference.
8. After the last round the cycle closes and the next opens. Each member chooses to continue or leave, and may change their beneficiary; the Organiser always continues. The Organiser sets the payout order for those continuing and starts the new cycle; anyone who has not chosen by then leaves.
9. Any current member can set a cover photo. The stokvel page and the list show that photo, with the name over a gradient so it stays readable.

## 13. Files created

| File | Purpose | Added in |
|---|---|---|
| `docs/stokvel_integration.md` | This tracking document | |
| `docs/stokvel_test_plan.md` | Every test the brief requires, the test or ticket that covers it, its owner and status | #266 |
| `contracts/` (Hardhat 2, Solidity 0.8.24, OpenZeppelin v5) | Contract project; `npm ci && npx hardhat test` | #282 |
| `contracts/src/StokvelVault.sol` | The stokvel contract (section 1) | #282 |
| `contracts/test/` | Tests: setup, contribute, pause, views, randomised invariants, ABI drift; `helpers.ts` has the fixtures and `uuidToBytes32`, the reference ID packing | #282, #291, #285 |
| `contracts/src/mocks/` | Test-only tokens (`MockUCTUSD`, `ReentrantToken`, `FeeOnTransferToken`); never deployed | #282 |
| `contracts/smart_contracts_changes.md` | Per-ticket log of contract changes and decisions | #282 |
| `contracts/hardhat.config.ts` | Compiler settings (#282); `xrplEvmTestnet` network, explorer verification, `contracts/.env` and root `.env` loading (#284) | #282, #284 |
| `contracts/scripts/deploy.ts` | Deploy script (`npm run deploy:local`, `npm run deploy:testnet`) | #284 |
| `contracts/deployments/xrplEvmTestnet.json` | Deployed address, block, tx hash and constructor arguments (written by the deploy script) | #284 |
| `contracts/scripts/verify-sourcify.js` | Verifies the recorded deployment on Sourcify v2 (`npm run verify:sourcify`); the explorer's verifier lacks solc 0.8.24 | #284 |
| `contracts/abi/StokvelVault.json` | Exported ABI the backend loads | #285 |
| `contracts/scripts/export-abi.js` | Writes the ABI from the build (`npm run export:abi`) | #285 |
| `contracts/README.md` | Contract overview: trust assumption, rules, roles, IDs, backend usage, deploy | #285 |
| `docs/adr/0002-one-contract-many-stokvels.md` | ADR for D4 (one contract holds every stokvel) | #285 |
| `api/remitx_api/models/orm/stokvel.py`, `stokvel_member.py`, `stokvel_invitation.py` | Group tables (section 3) | #226 |
| `api/remitx_api/repositories/stokvel_repository.py`, `stokvel_member_repository.py`, `stokvel_invitation_repository.py` | Their repositories | #226 |
| `api/alembic/versions/V20261009_1801__stokvel_group_tables.py` | Tables, RLS policies and lookup functions | #226 |
| `api/tests/test_stokvel_group_models.py` | Constraints (SQLite) and RLS (`postgres` lane) | #226 |
| `api/remitx_api/models/orm/stokvel_cycle.py`, `stokvel_round.py`, `stokvel_cycle_member.py` | Cycle tables (section 3) | #227 |
| `api/remitx_api/repositories/stokvel_cycle_repository.py` | Reads for cycles, rounds and cycle members | #227 |
| `api/alembic/versions/V20261014_1200__stokvel_cycle_tables.py` | Cycle tables, `stokvels.current_cycle_id`, RLS policies (one per operation, no delete), lookup functions and the same-stokvel trigger | #227 |
| `api/tests/test_stokvel_cycle_models.py` | Constraints (SQLite); RLS, no deletes and the same-stokvel trigger (`postgres` lane) | #227 |
| `api/remitx_api/models/orm/stokvel_contribution.py` | Contributions table (section 3) and `StokvelContributionStatus` | #228 |
| `api/remitx_api/repositories/stokvel_contribution_repository.py` | Reads for contributions; R2-11 adds the open round and the contributions' rand totals for the limits | #228, #233 |
| `api/remitx_api/controllers/stokvel_contribution_controller.py` | The contribution use case: checks, pending legs, enqueue; `contribution_fee_share` | #233 |
| `api/alembic/versions/V20261016_1352__stokvel_contribution_legs_and_rand_value.py` | `fiat_tx_id`, `token_tx_id`, `fee_tx_id`, `amount_zar` on `stokvel_contributions` | #233 |
| `api/alembic/versions/V20261016_1500__transactions_rls_stokvel_account_legs.py` | Two `transactions` policies: members read legs on their stokvel's `STOKVEL` account; current members record only the token leg (Treasury → their stokvel's account); no update or delete | #233 |
| `api/tests/test_stokvel_contributions_route.py` | The route's rules, legs, fee and daily and monthly limits, and a duplicate that slips past the paid check (SQLite); the token leg, member-only reads and two payments at once under RLS (`postgres` lane) | #233 |
| `api/remitx_worker/stokvel_tasks.py` | The stokvel worker tasks: `stokvel.submit_contribution`, `stokvel.confirm_contribution` (#234); `stokvel.start_cycle`, `stokvel.register_started_cycles` (#232) | #234, #232 |
| `api/remitx_api/routes/admin/stokvels.py` | `POST /admin/stokvels/{id}/rounds/{n}/finalise` | #247 |
| `api/remitx_api/services/stokvel_contract_read.py` | Read-only vault calls from the API: `paused` (#244); `finalise_readiness` (#247) | #244, #247 |
| `api/alembic/versions/V20261024_2100__add_stokvel_round_finalise_permission.py` | `stokvel:round:finalise` and the compliance officer grant | #247 |
| `api/tests/test_admin_stokvel_finalise.py` | Ready, not ready, already released (including a closed cycle's round once the next is forming), paused, and the chain read's classification | #247, #237 |
| `api/remitx_worker/stokvel_contract.py` | Wrapper over the vault: `contribute`, the Treasury allowance, revert decoding (#234); `get_stokvel`, `create_stokvel`, `start_cycle` (#232); R3-04 adds `finalise` | #234, #232 |
| `api/remitx_worker/abi/StokvelVault.json` | Copy of `contracts/abi/StokvelVault.json` for the worker image (built from `api/` only); a test fails if they differ | #234 |
| `api/remitx_worker/stokvel_sync.py` | Applies the vault's events to the database (`apply_event`); `CycleClosed` also opens the next cycle (#237) | #235, #237 |
| `api/remitx_api/models/orm/stokvel_held_event.py` | Events the sync holds: waiting, or failed for a person | #235 |
| `api/remitx_worker/stokvel_ledger.py` | `record_mined` and `record_pool_release`: recording a mined contribution and a released pool, each through one guard shared by its task and the event sync | #235, #241 |
| `api/remitx_worker/stokvel_release.py` | `stokvel.release_pool`: sends `finalise` for a round due with time and records the release from the receipt. `stokvel.release_due_rounds` (#248): the beat task that queues it | #241, #248 |
| `api/remitx_worker/stokvel_payouts.py` | `stokvel.settle_payout`: turns a released payout into a quote, legs and remittance, and hands it to settlement (#243); `queue_released_payouts`, run by the event sync; `record_settlement`, which finishes the payout (#243) | #242 |
| `api/tests/test_stokvel_payout_retry.py` | Payout settlement against a faked chain and a list for a broker: the hand-off, the whole chain, every message delivered twice, every step retried after settling or failing, the sweep and the hand-off together, each way a burn fails, and no receipt | #243 |
| `api/tests/test_stokvel_three_rounds.py` | The brief's scenario end to end: three members set up through the API, three rounds contributed, each pool released by a faked vault that keeps D5 and D12, synced, paid to the scheduled member's beneficiary and burnt, then the cycle closed and the member screen checked. Its `FakeVault` also refuses an early or repeated `finalise` and answers the API's readiness read, for R6-05 | #269, #270 |
| `api/tests/test_stokvel_blocked_duplicate_early.py` | The demo's three refusals: a round held while one member has not paid round N+1, then released by their payment; a second contribution to a round (409, no second debit) and a contribution message delivered twice (one contract call); the admin's Release payout refused before the payout time, accepted after it, then refused as already released | #270 |
| `api/alembic/versions/V20261019_1700__stokvel_payouts_release_hash_not_unique.py` | Drops the unique constraint on `stokvel_payouts.release_tx_hash`: one `contribute` can release several due rounds in one transaction | #241 |
| `api/alembic/versions/V20261020_1700__stokvel_payouts_settle_queued_at.py` | Adds `stokvel_payouts.settle_queued_at`, when the event sync last queued the payout | #242 |
| `api/tests/test_worker_stokvel_release.py` | `record_pool_release` (once, races, conflicts, a short `STOKVEL`) and `release_pool` with the chain faked (refusals, retries, reverts, redelivery, no receipt); `finalise` and `round_finalised` | #241 |
| `api/tests/test_worker_stokvel_release_due_rounds.py` | The scheduled release against a faked vault that applies the contract's release rule on a clock the test moves: paid early and released only at the payout time (the last round too), a late payment that releases the round itself, a double trigger, one round per run, pause, a stuck claim, failed reads and enqueues; `is_finalisable` | #248 |
| `api/remitx_api/models/orm/stokvel_sync_state.py` | The event sync's cursor | #235 |
| `api/alembic/versions/V20261018_1000__stokvel_sync_state.py` | The cursor table and its worker-only policy | #235 |
| `api/tests/test_stokvel_sync_events.py` | The sync: each event, replays, the cursor, crashes, races, RPC errors, decoding; the cursor's row-level security (`postgres` lane) | #235 |
| `api/tests/test_worker_stokvel_contribution.py` | The two tasks with the chain faked: duplicate messages, reverts, refusals, retries, no receipt; the contract wrapper | #234 |
| `api/alembic/versions/V20261016_0901__stokvel_contributions.py` | Contributions table, partial unique index, composite foreign keys, RLS policies (one per operation, no customer update, no delete) | #228 |
| `api/tests/test_stokvel_contribution_model.py` | Pay once (retry after failure), stay inside the cycle, status columns (SQLite); RLS reads, own-row inserts, worker-only updates, no deletes (`postgres` lane) | #228 |
| `api/remitx_api/models/orm/stokvel_payout.py` | Payout table (section 3): `StokvelPayout`, `StokvelPayoutReleaseStatus` (`remittance_status` uses `TransactionStatus`) | #240 |
| `api/remitx_api/repositories/stokvel_payout_repository.py` | Reads for payouts; R3-04 to R3-06 add the claims | #240 |
| `api/alembic/versions/V20261016_1200__stokvel_payouts.py` | Payout table, RLS policies (one per operation, customers never write, no delete) and the scheduled-member trigger | #240 |
| `api/tests/test_stokvel_payout_model.py` | One payout per round, the status and release CHECKs, a retried release, unique legs, hashes and quotes (SQLite); trigger, RLS (customers read, workers and admin routes write, nobody deletes) and migration round trip (`postgres` lane) | #240 |
| `api/alembic/versions/V20261011_1000__stokvel_ledger_account_and_types.py` | `STOKVEL` account type and balance CHECK, stokvel transaction types, `stokvels.account_id` | #238 |
| `api/alembic/versions/V20261011_1001__quote_sender_stokvel.py` | Nullable `quotes.sender_user_id`, `quotes.stokvel_id`, `quotes_one_sender` | #239 |
| `api/alembic/versions/V20261011_1002__add_transactions_evm_tx_hash.py`, `V20261011_1003__backfill_transactions_evm_tx_hash.py` | `evm_tx_hash` added beside `xrpl_tx_hash`, then backfilled | #239 |
| `api/alembic/versions/V20261011_1004__rename_xrpl_wallet_to_evm_wallet.py` | Treasury type `REMITX_EVM_WALLET` and label "RemitX Treasury Wallet" | #239 |
| `api/tests/test_stokvel_ledger.py` | Stokvel account, transaction types and stokvel quote sender | #238, #239 |
| `api/tests/test_evm_names_migration.py` | Backfill and treasury rename on Postgres (`postgres` lane) | #239 |
| `frontend/app/lib/chain.ts`, `chain.test.ts`, `frontend/app/components/chain/tx-hash.tsx` | Chain from a hash's format, explorer links for XRPL and EVM, `shortHash`; `ChainTxHash` replaces `components/xrpl/tx-hash.tsx` and `components/transfers/xrpl-hash.tsx` (deleted) | #257 |
| `api/tests/test_stokvel_payout_reads.py` | A stokvel's payout still lists for its recipient (transfers, dashboard) and in the admin operations totals; the recipient sees the stokvel's name, also outside the stokvel under Postgres row-level security | #239 |
| `docs/adr/0004-stokvel-ledger-account.md` | ADR for D9 (a stokvel has its own ledger account) | #238 |
| `frontend/app/lib/stokvels.ts` | Member queries and mutations on the generated client; helpers for the member screen. The collecting round is the response field `open_round`. Detail types come from `~/client` (#258). `stokvelPollInterval` and `stokvelDetailPollInterval` refetch the list, a stokvel page and the admin rounds page while they are open | #251, #258 |
| `frontend/app/lib/audit-entry.ts`, `audit-entry.test.ts` | Audit areas and stokvel actions for the filters; `auditTxHash` and `isStokvelEntry` for the entry detail | #261 |
| `frontend/app/lib/stokvels.mock.ts` | Deleted (#258). It mocked `GET /stokvels`, `GET /stokvels/{id}` and a contract status the API does not return | #251 |
| `frontend/app/lib/stokvels.test.ts` | Helper tests. Mock-scenario tests removed with the mock (#258) | #251, #258 |
| `frontend/app/routes/app/stokvels.tsx`, `stokvel.tsx` | Member list (`GET /stokvels`) and detail (`GET /stokvels/{id}`). A cover photo is the list thumbnail and the detail banner | #251, #258 |
| `frontend/app/components/stokvels/stokvel-cover.tsx` | Cover banner and list thumbnail, with the name on a gradient, and the upload | |
| `frontend/app/routes/admin/stokvel-contract.tsx` | Admin contract page (state only; pause and resume in #256); nav group "Stokvels" in `admin.routes.ts` | #251 |
| `frontend/app/lib/stokvel-contract.ts`, `stokvel-contract.mock.ts`, `stokvel-contract.test.ts` | Admin contract page wired to `GET /admin/stokvel-contract` and pause/unpause; mock kept for unit tests | #256 |
| `api/tests/test_worker_treasury_send_lock.py` | The Treasury send lock: a no-op on SQLite; on Postgres (`postgres` lane) an exclusive transaction-level advisory lock, held only inside the block and released when the send raises | #278 |
| `platform_wallet/scripts/test_burn.py` | One tiny real `burn(uint256)` from the Treasury to confirm the burn method (section 8); a dry run unless `--send`, and refuses any chain, token or wallet but the expected ones | #278 |
| `api/remitx_api/controllers/stokvel_controller.py` | Create a stokvel; list the caller's stokvels and pending invitations (R2-07); read one stokvel (R2-14, #236); set its cover photo | #229 |
| `api/remitx_api/models/orm/stokvel_cover.py`, `api/remitx_api/repositories/stokvel_cover_repository.py` | Cover photo metadata. The bytes stay in object storage | |
| `api/alembic/versions/V20261027_2134__stokvel_cover_photo.py` | `stokvel_covers`, current-member policies, and the fixed object-key trigger | |
| `api/tests/test_stokvel_cover.py` | Upload rules on SQLite; current-member writes and the key trigger under row-level security (`postgres` lane) | |
| `api/remitx_api/routes/stokvels.py` | `POST /stokvels`, `GET /stokvels`, `GET /stokvels/{id}` (#236); `POST /stokvels/{id}/cover`; `POST /stokvels/{id}/invitations` (#230) | #229 |
| `api/tests/test_stokvel_member_view.py` | `GET /stokvels/{id}` on SQLite: the forming screen, a missing rate, 404 for a non-member, the caller's fee only, a payout with no remittance yet, every invitation of any status newest first, and the reference on an answered invitation for the Organiser only | #236, #375 |
| `api/remitx_api/routes/stokvels.py` | `POST /stokvels`, `GET /stokvels`, `GET /stokvels/{id}` (#236); `POST /stokvels/{id}/cover`; `POST /stokvels/{id}/invitations` (#230); `POST /stokvels/{id}/members/me/continuation` (#237) | #229 |
| `api/tests/test_stokvel_member_view.py` | `GET /stokvels/{id}` on SQLite: the forming screen, a missing rate, 404 for a non-member, the caller's fee only, a payout with no remittance yet, and the closed cycle in `previous_cycle` while the next forms | #236, #237 |
| `api/remitx_api/models/schemas/stokvel.py` | `StokvelCreateRequest`, `StokvelRead`, `StokvelInvitationRead`, `StokvelListRead`; `StokvelInvitationCreateRequest`, `SentStokvelInvitationRead` (#230) | #229 |
| `api/remitx_api/errors/stokvels.py` | `KycNotApprovedToCreateStokvelError` (403), `StokvelCurrencyAccountMissingError` (400) | #229 |
| `api/tests/test_stokvels_route.py` | Both routes on SQLite: refusals, one transaction, validation, and the caller scoping that SQLite needs | #229 |
| `api/tests/test_stokvels_row_security.py` | Create and list under Postgres row-level security, and the membership trigger (`postgres` lane) | #229 |
| `api/alembic/versions/V20261017_1820__stokvel_member_write_rules.py` | `stokvel_members` and `stokvel_invitations` policies per operation, their triggers, and the `kyc_latest_status` and `stokvel_active_member_count` lookups (section 3) | #230 |
| `api/remitx_api/controllers/stokvel_invitation_controller.py` | Invite, accept and decline (R2-08); revoke (R2-16) | #230, #297 |
| `api/remitx_api/routes/stokvel_invitations.py` | `POST /invitations/{id}/accept`, `POST /invitations/{id}/decline`; `POST /invitations/{id}/revoke` (#297) | #230, #297 |
| `api/tests/test_stokvel_invitations_route.py` | The four routes on SQLite (the #209 examples, every refusal, one transaction) and under Postgres row-level security (KYC lookup, cap for an invitee, two accepts for the last place, the Organiser's revoke, members reading every invitation on `GET /stokvels/{id}`) | #230, #297, #375 |
| `api/alembic/versions/V20261027_1847__stokvel_payout_name.py` | The `stokvel_payout_name` lookup: a payout's recipient reads the stokvel's name, which row-level security hides (section 8, product question 6) | |
| `api/tests/test_stokvel_member_row_security.py` | The `stokvel_members` and `stokvel_invitations` write rules, their triggers, and the lookups (`postgres` lane) | #230 |
| `api/remitx_api/controllers/stokvel_setup_controller.py` | Payout order and beneficiary for the forming cycle (R2-09); continuing or leaving after a cycle (R2-15) | #231, #237 |
| `api/tests/test_stokvel_setup_route.py` | Both setup routes on SQLite (every refusal, re-ordering in place, former members, on-demand cycle 1) and under Postgres row-level security | #231 |
| `api/remitx_api/controllers/stokvel_cycle_controller.py` | Starting a cycle (R2-10): readiness checks, the schedule, lapsing invitations, locking, then the enqueue. Opening the next cycle and who goes into it (R2-15) | #232, #237 |
| `api/alembic/versions/V20261022_1000__stokvel_organiser_ends_membership.py` | The Organiser may end a fellow member's membership (`stokvel_members_update`, `stokvel_member_identity_fixed`) | #237 |
| `api/tests/test_stokvel_continuation.py` | The continuation route, the next cycle's payout order and start, a second cycle end to end, and the same under Postgres row-level security | #237 |
| `api/alembic/versions/V20261019_1051__stokvel_cycle_chain_registration.py` | `stokvel_cycles.start_tx_hash`, `start_block_number`, `registered_at` and their CHECKs | #232 |
| `api/alembic/versions/V20261019_1052__organiser_lapses_stokvel_invitations.py` | `stokvel_invitations_update` lets the Organiser record `lapsed` | #232 |
| `api/tests/test_stokvel_start_cycle.py` | The start route on SQLite (the ticket's done-when cases, every refusal, the schedule rules, whole-second UTC times) and under Postgres row-level security (the Organiser's start, the lapse policy) | #232 |
| `api/tests/test_worker_stokvel_start_cycle.py` | `stokvel.start_cycle` and `stokvel.register_started_cycles` against a faked chain (create then start, already registered, already open, a duplicate racing the hash owner, redelivery, a failed record retried, chain and database disagreeing, refusals, retries, reverts, the sweep), and the wrapper's encoding | #232 |
| `tools/loadtest/fake_evm_worker.py` (was `fake_xrpl_worker.py`) | The load test's real worker with the EVM burn and receipt simulated | #267 |
| `tools/loadtest/qa_burn_timings.sql` (was `qa_xrpl_timings.sql`) | QA's real EVM burn timings, for calibrating the load test | #267 |
| `frontend/app/lib/stokvel-create.ts`, `stokvel-create.test.ts` | Create wizard state (URL search params), validation, the resolved Stokvel currency, and the `POST /stokvels` body (fiat converted to UCTUSD) | #252 |
| `frontend/app/hooks/use-token-rate.ts` | Live token units per 1 unit of the Stokvel currency, from the quote preview: shows fixed token amounts in fiat and fixes the amount at creation | #252 |
| `frontend/app/routes/app/stokvel-new.tsx` | The wizard page at `app/stokvels/new` (KYC-approved users only) | #252 |
| `frontend/app/components/stokvels/create-progress.tsx`, `create-name-step.tsx`, `create-amount-step.tsx`, `create-review-step.tsx` | Wizard steps; the amount step previews a full round with `POST /quotes/preview-quote`: the pool, each member's fee share on top, and the full pool to the beneficiary | #252 |
| `frontend/app/lib/stokvel-errors.ts`, `stokvel-errors.test.ts` | Section 6 codes → user wording; `contributeRefusal` adds the ledger's balance, limit and verification refusals | #254 |
| `frontend/app/hooks/use-fee-share.ts` | Estimate of a member's fee share for a round, from the quote preview, until the API returns `fee_amount` | #254 |
| `frontend/app/components/stokvels/invite-member-form.tsx`, `invitation-card.tsx`, `contribution-at-rate.tsx` | Organiser's invite-by-reference form; invitee's card with Accept and Decline; the "R500.00 at today's rate" figure | #253, #299 |
| `frontend/app/components/stokvels/stokvel-invitations.tsx` | Each invitation is a card with the invitee's avatar (the Organiser's beneficiary photo when the name matches) and status, and the Organiser's Revoke | #299 |
| `frontend/app/lib/stokvel-schedule.ts`, `stokvel-schedule.test.ts` | Round schedule from a cadence, first payout and pay-by days, in the start-cycle body's shape, checked like the contract's `_validateSchedule` | #255 |
| `frontend/app/components/stokvels/payout-beneficiary-card.tsx`, `cycle-setup.tsx`, `setup-wizard.tsx`, `payout-order-list.tsx` | Member's payout beneficiary choice (the send-money beneficiary picker, with avatars); Organiser setup stepper (people, invite-list payout order, schedule, start). The order is dragged and saved after a short pause. Start stays closed until every invite on that list is accepted | #255 |
| `frontend/app/components/stokvels/pot-ring.tsx`, `contribution-panel.tsx`, `payout-status.tsx`, `round-schedule.tsx` | Member screen pieces: the pot and this round's contribution share one card, Pay now with the confirm sheet and refusals, the payout tracker, payout order and round history (also the closed cycle's, while the next forms) | #254, #237 |
| `frontend/app/lib/stokvel-admin.ts`, `stokvel-admin.mock.ts`, `stokvel-admin.test.ts`, `frontend/app/routes/admin/stokvel-rounds.tsx`, `frontend/app/components/admin/stokvel-finalise-button.tsx` | Admin rounds list and manual release wired to `GET /admin/stokvels/rounds` and finalise; mock kept for unit tests. Sidebar needs `stokvel:round:finalise` | #260, #247 |
| `tools/seeder/remitx_seeder/stories/stokvel.py` | The stokvel demo story: three named members, verified and funded, a stokvel ready to start and a second with an invitation pending | #268 |
| `tools/seeder/remitx_seeder/stories/stokvel_plan.py` | Who the demo's members are and which stokvels they are in. Plain data with no backend import, so scenario validation in the seeder UI stays free of `remitx_api` | #268 |
| `tools/seeder/scenarios/demo.json` | The `demo` scenario: Reset, then seed it, to prepare the demo | #268 |
| `tools/seeder/tests/test_stokvel_demo.py` | One seed of the `demo` scenario, the state it leaves, and both cycles starting through `StokvelCycleController` | #268 |
| `api/remitx_api/services/stokvel_reconciliation_service.py` | `check_pool_reconciliation`: Treasury UCTUSD the ledger expects, against a balance the caller read on-chain, plus the in-flight net | #245 |
| `api/scripts/check_pool_reconciliation.py` | Demo command: read the Treasury's UCTUSD and print pass or fail, and the in-flight net. Not part of the API process | #245 |
| `api/alembic/versions/V20261024_2105__one_token_burn_per_quote.py` | Partial unique index `uq_transactions_one_token_burn_per_quote` | #245 |
| `api/tests/test_stokvel_reconciliation.py` | The index, burn equals the pool while float remains, three rounds balance and an over-burn does not | #245 |

## 14. Functions created

| Function | File | Purpose | Added in |
|---|---|---|---|
| `createStokvel`, `startCycle`, `contribute`, `finalise`, `pause`, `unpause` | `contracts/src/StokvelVault.sol` | Contract interface (section 1) | #282 |
| `getStokvel`, `getCycle`, `hasPaid`, `roundPool`, `isFinalisable`, `isMember`, `paidCount`, `openRound` | `contracts/src/StokvelVault.sol` | Contract views (section 1) | #282 |
| `uuidToBytes32` | `contracts/test/helpers.ts` | UUID → left-aligned `bytes32`; the backend's helper must match | #282 |
| `npm run deploy:local`, `npm run deploy:testnet` | `contracts/scripts/deploy.ts` | Dry run on a local chain; deploy to the XRPL EVM Testnet | #284 |
| `npm run export:abi` | `contracts/scripts/export-abi.js` | Compile and write `contracts/abi/StokvelVault.json` | #285 |
| `stokvel_is_member`, `stokvel_is_organiser`, `stokvel_has_pending_invitation` (SQL) | `api/alembic/versions/V20261009_1801__stokvel_group_tables.py` | RLS lookups (section 3) | #226 |
| `stokvel_member_account_is_fiat` (SQL) | `api/alembic/versions/V20261009_1801__stokvel_group_tables.py` | Member's fiat account in the stokvel currency | #226 |
| `stokvel_cycle_is_member`, `stokvel_cycle_is_organiser`, `stokvel_member_is_user` (SQL) | `api/alembic/versions/V20261014_1200__stokvel_cycle_tables.py` | RLS lookups for the cycle tables (section 3) | #227 |
| `stokvel_cycle_member_same_stokvel` (SQL trigger function) | `api/alembic/versions/V20261014_1200__stokvel_cycle_tables.py` | `BEFORE INSERT OR UPDATE OF cycle_id, member_id` on `stokvel_cycle_members`: refuses a member row from a different stokvel than the cycle (SQLSTATE 23514) | #227 |
| `StokvelCycleRepository.get_open_cycle`, `.get_cycle_rounds`, `.get_cycle_members` | `api/remitx_api/repositories/stokvel_cycle_repository.py` | A stokvel's open cycle; a cycle's rounds in order and members in payout order | #227 |
| `StokvelContributionRepository.get_member_contribution`, `.get_round_contributions`, `.get_paid_member_ids` | `api/remitx_api/repositories/stokvel_contribution_repository.py` | A member's live (not failed) contribution to a round; every attempt at a round, oldest first; the members whose contribution to a round is confirmed | #228 |
| `stokvel_payout_member_is_scheduled` (SQL trigger function) | `api/alembic/versions/V20261016_1200__stokvel_payouts.py` | `BEFORE INSERT OR UPDATE OF cycle_id, round, member_id` on `stokvel_payouts`: refuses a member whose `payout_position` is not the round (SQLSTATE 23514) | #240 |
| `stokvel_cycle_member_position_is_paid` (SQL trigger function) | `api/alembic/versions/V20261016_1200__stokvel_payouts.py` | `BEFORE UPDATE OF payout_position` on `stokvel_cycle_members`: refuses changing the position of a member who already has a payout for that round (SQLSTATE 23514), the mirror of `stokvel_payout_member_is_scheduled` | #240 |
| `StokvelPayoutRepository.get_round_payout`, `.get_cycle_payouts` | `api/remitx_api/repositories/stokvel_payout_repository.py` | One round's payout; a cycle's payouts in round order | #240 |
| `AccountRepository.create_stokvel_account`, `AccountRepository.get_stokvel_account` | `api/remitx_api/repositories/account_repository.py` | Create a stokvel's `STOKVEL` account and link it; find it by stokvel | #238 |
| `burn_tokens(amount, *, on_signed=None, w3=None)` | `api/remitx_worker/evm_service.py` | Burn exactly `amount` UCTUSD from the Treasury with `burn(uint256)`; returns the tx hash without waiting | #278 |
| `submit_transaction(tx, w3=None, *, on_signed=None)` | `api/remitx_worker/evm_service.py` | Changed: `on_signed(tx_hash)` runs after signing and before the send, so the caller can store the hash first; the send holds `treasury_send_lock` from the nonce read until the nonce has moved on. Raises `TransactionRejected` when the RPC answers the send with a known refusal (for example insufficient funds for gas); any other error is left uncertain, and "already known" counts as sent. Every Treasury send must go through it | #278 |
| `TransactionReverted` | `api/remitx_worker/evm_service.py` | Raised by `wait_for_receipt` when a mined transaction reverted (a `RuntimeError`) | #278 |
| `TransactionRejected` | `api/remitx_worker/evm_service.py` | Raised by `submit_transaction` when the RPC refuses the send (a `RuntimeError`): the transaction can never be mined, so the burn fails its group at once (`event=settlement.burn_rejected`) | #278 |
| `transaction_status(tx_hash, w3=None)` | `api/remitx_worker/evm_service.py` | Whether the RPC holds a transaction (`pending`) or has no record of it (`unknown`). Diagnostic only, for the `event=settlement.burn_unconfirmed` log line; never grounds for sending again | #278 |
| `treasury_send_lock` | `api/remitx_worker/db.py` | Transaction-level Postgres advisory lock (`pg_advisory_xact_lock`, in a transaction of its own) that lets one Treasury transaction be built and sent at a time. No unlock statement, so it is safe through Neon's transaction pooler; a no-op on SQLite | #278 |
| `_burn_hash_values`, `_BURN_HASH_COLUMN` | `api/remitx_worker/tasks.py` | The only place the worker names the burn hash columns: writes `evm_tx_hash` and `xrpl_tx_hash`, reads `evm_tx_hash`. Update here when #239 drops `xrpl_tx_hash` | #278 |
| `StokvelController.create_stokvel`, `.list_stokvels`, `.get_stokvel` | `api/remitx_api/controllers/stokvel_controller.py` | Create a stokvel with its ledger account and the Organiser's membership in one transaction; the caller's current stokvels and pending invitations; one stokvel for the member screen (#236) | #229 |
| `StokvelRepository.list_for_member` | `api/remitx_api/repositories/stokvel_repository.py` | Stokvels a user is a current member of, newest first, with each one's current member count; scoped by user | #229 |
| `StokvelContributionController.contribute` | `api/remitx_api/controllers/stokvel_contribution_controller.py` | Record a contribution to the open round with its pending legs, then enqueue `stokvel.submit_contribution` | #233 |
| `contribution_fee_share` | `api/remitx_api/controllers/stokvel_contribution_controller.py` | The member's equal share of the round's payout fee and margin, worked out on the pool by `remittance_fee_and_margin` (no margin when the recipient is paid in the Stokvel currency), rounded up to the cent, paid on top (D6) | #233 |
| `remittance_fee_and_margin` | `api/remitx_api/services/quote_service.py` | FSE's fee and margin on a sender amount, factored out of `price_remittance` so a stokvel contribution prices its fee share with the same rule | #233 |
| `StokvelContributionRepository.open_round`, `.contributed_zar` | `api/remitx_api/repositories/stokvel_contribution_repository.py` | The round a contribution goes into (contract's `openRound` rule); contributions' rand totals for the sending limits | #233 |
| `StokvelMemberRepository.get_active_member` | `api/remitx_api/repositories/stokvel_member_repository.py` | A user's current membership of a stokvel | #233 |
| `quote_service.token_rates`, `TokenRates` | `api/remitx_api/services/quote_service.py` | A currency's and the rand's token rates, looked up once so a contribution can price after locking the member without touching the rate store (a lookup may commit) | #233 |
| `quote_service.token_to_fiat` | `api/remitx_api/services/quote_service.py` | A UCTUSD amount's cost in a fiat currency, from `TokenRates`: the stored USD quote itself, not a rounded inverse | #233 |
| `queue_service.enqueue_submit_contribution` | `api/remitx_api/services/queue_service.py` | Queue `stokvel.submit_contribution` (registered in `stokvel_tasks`, #234) | #233 |
| `queue_service.enqueue_confirm_contribution` | `api/remitx_api/services/queue_service.py` | Queue `stokvel.confirm_contribution` with the outcome: the hash and block, or `None` and the error | #234 |
| `submit_contribution`, `confirm_contribution` (`stokvel.*` tasks) | `api/remitx_worker/stokvel_tasks.py` | Send a claimed contribution's `contribute`, then record the outcome (section 4) | #234 |
| `stokvel_contract.contribute`, `.ensure_allowance`, `.error_name`, `ContractRefused` | `api/remitx_worker/stokvel_contract.py` | Send `contribute` with packed IDs; top up the Treasury's allowance for the vault; name a revert from the vault or the token; a call whose gas estimate reverts, never sent | #234 |
| `evm_service.treasury_address` | `api/remitx_worker/evm_service.py` | The Treasury Wallet's address, for reads, without touching the key | #234 |
| `sync_events` (`stokvel.sync_events` task) | `api/remitx_worker/stokvel_tasks.py` | Read the vault's events since the cursor and apply them, range by range (section 4) | #235 |
| `stokvel_sync.apply_event` | `api/remitx_worker/stokvel_sync.py` | Apply one event: `ContributionMade`, `RoundFinalised` (#241), `CycleClosed`; report `WAITING` for one that cannot apply yet, or raise `EventNeedsAPerson` when the chain and the database disagree | #235, #241 |
| `stokvel_ledger.record_mined` | `api/remitx_worker/stokvel_ledger.py` | Confirm a contribution and move its legs' balances, guarded on `pending`/`processing` | #235 |
| `stokvel_ledger.record_pool_release` | `api/remitx_worker/stokvel_ledger.py` | Record a released pool: payout `released` with its hash and block, `STOKVEL` → Treasury leg booked and balances moved, guarded on `pending`/`processing`; raises `ReleaseConflict` (another member or hash, or `failed`) before writing Moves `STOKVEL` before the Treasury, the row-lock order `record_mined` takes, so the two cannot deadlock on Postgres | #241, #242 |
| `stokvel_ledger.ensure_payout`, `scheduled_member` | `api/remitx_worker/stokvel_ledger.py` | A round's payout row, created `pending` for the member whose payout position is the round if missing; a concurrent insert is read back | #241 |
| `stokvel.release_pool` | `api/remitx_worker/stokvel_release.py` | Claim the payout, send `finalise`, wait, record (section 4) | #241 |
| `stokvel.release_due_rounds` | `api/remitx_worker/stokvel_release.py` | Beat: queue `release_pool` for each cycle's next round that is overdue, fully paid and `isFinalisable` (section 4) | #248 |
| `stokvel_contract.is_finalisable` | `api/remitx_worker/stokvel_contract.py` | Read `isFinalisable(id, round)`: whether `finalise` would succeed now | #248 |
| `stokvel_contract.finalise`, `round_finalised` | `api/remitx_worker/stokvel_contract.py` | Send `finalise(id, round)` from the Treasury; read the vault's `RoundFinalised` events from a receipt | #241 |
| `queue_service.enqueue_release_pool` | `api/remitx_api/services/queue_service.py` | Queue `stokvel.release_pool` (for R3-11, R3-10) | #241 |
| `stokvel.settle_payout` | `api/remitx_worker/stokvel_payouts.py` | Check the beneficiary, price, then create the quote, legs and remittance and move the payout's remittance `pending → processing` in one commit (section 4); then queue `settle_remittance` (#243) | #242 |
| `stokvel_payouts.record_settlement` | `api/remitx_worker/stokvel_payouts.py` | Called by `confirm_treasury_burn` in its commit: the payout whose remittance the quote is, `processing → confirmed` with the burn hash or `processing → failed`; None for any other remittance | #243 |
| `stokvel_payouts.queue_released_payouts` | `api/remitx_worker/stokvel_payouts.py` | Queue `stokvel.settle_payout` for each released payout with no quote yet: once on release, then at most every `REQUEUE_AFTER` (5 minutes, marked by `settle_queued_at`), longest waiting first, at most 50 a run; run at the end of every `stokvel.sync_events` | #242 |
| `quote_service.price_stokvel_payout` | `api/remitx_api/services/quote_service.py` | Price a payout: `token_amount` the pool, `sender_amount` the pool at the live rate in the Stokvel currency, converted to the payout currency; no fee, margin or limits (D6, D8). Returns the pricing and the sender amount | #242 |
| `queue_service.enqueue_settle_payout` | `api/remitx_api/services/queue_service.py` | Queue `stokvel.settle_payout` | #242 |
| `stokvel_ledger.treasury_account_id` | `api/remitx_worker/stokvel_ledger.py` | The Treasury Wallet's UCTUSD ledger account, shared by the release and the payout | #242 |
| `stokvel_contract.fetch_logs`, `decode_log`, `ContractEvent` | `api/remitx_worker/stokvel_contract.py` | Read the synced events' raw logs in a block range (the RPC call only), and decode one log, so a log that will not decode is not taken for an RPC failure. Topics from `eth_utils.event_abi_to_log_topic`, built once | #235 |
| `evm_service.bytes32_to_uuid` | `api/remitx_worker/evm_service.py` | A packed `bytes32` ID back to its UUID; None for an ID not packed from one | #235 |
| `StokvelNotFoundError`, `NotACycleMemberError`, `CycleNotOpenError`, `NoOpenRoundError`, `ContributionAlreadyPaidError`, `ContributionInsufficientBalanceError` | `api/remitx_api/errors/stokvels.py` | The contribution refusals (section 6) | #233 |
| `DomainError.code` and the error handler | `api/remitx_api/errors/base.py`, `api/remitx_api/app.py` | Optional machine-readable code, added to the error body when set (section 6) | #233 |
| `KycApplicationRepository.get_standing` (changed) | `api/remitx_api/repositories/kyc_application_repository.py` | Daily and monthly used amounts now add the member's stokvel contributions (`contributed_zar`) to their remittances (D8) | #233 |
| `contribute_to_stokvel` (route) | `api/remitx_api/routes/stokvels.py` | `POST /stokvels/{id}/contributions`, response `StokvelContributionRead` (`api/remitx_api/models/schemas/stokvel.py`) | #233 |
| `stokvel_account_is_member`, `stokvel_account_is_active_member`, `account_is_treasury_wallet` (SQL) | `api/alembic/versions/V20261016_1500__transactions_rls_stokvel_account_legs.py` | Whether a user is (or was, for the first) a member of the stokvel an account belongs to, and whether an account is the Treasury Wallet: the read and insert `transactions` policies | #233 |
| `StokvelInvitationRepository.list_pending_for_invitee` | `api/remitx_api/repositories/stokvel_invitation_repository.py` | A user's pending invitations, newest first, with the stokvel and the inviter; scoped by user. Leaves out deactivated stokvels (#230) | #229 |
| `StokvelInvitationRepository.list_for_stokvel` | `api/remitx_api/repositories/stokvel_invitation_repository.py` | A stokvel's invitations of every status, newest first, each with the invitee; the account reference only when asked for (the Organiser). Was `list_pending_for_stokvel` (pending only, #236) | #375 |
| `StokvelInvitationController.invite`, `.accept`, `.decline`, `.revoke` | `api/remitx_api/controllers/stokvel_invitation_controller.py` | Invite by account reference; accept (lock the stokvel, check KYC, account and cap, mark accepted, insert the member), decline, and the Organiser's revoke (#297), each in one transaction | #230, #297 |
| `stokvel_view` | `api/remitx_api/controllers/stokvel_controller.py` | A stokvel as a user sees it (`StokvelView`); was `StokvelController._view`, now shared with accepting | #230 |
| `StokvelRepository.lock` | `api/remitx_api/repositories/stokvel_repository.py` | The stokvel, `SELECT ... FOR UPDATE` | #230 |
| `StokvelRepository.get_stokvel_names` | `api/remitx_api/repositories/stokvel_repository.py` | Names by stokvel id in one query, for the payouts on the transfers list and page, the dashboard and account history; `stokvel_payout_name` on Postgres | |
| `stokvel_payout_name` (SQL) | `api/alembic/versions/V20261027_1847__stokvel_payout_name.py` | A stokvel's name, for a customer it has paid | |
| `StokvelMemberRepository.count_active` | `api/remitx_api/repositories/stokvel_member_repository.py` | Current members of a stokvel; `stokvel_active_member_count` on Postgres | #230 |
| `StokvelInvitationRepository.set_status_if_pending` | `api/remitx_api/repositories/stokvel_invitation_repository.py` | Answer an invitation, guarded by `status = 'pending'`; whether it changed | #230 |
| `KycApplicationRepository.is_other_user_verified` | `api/remitx_api/repositories/kyc_application_repository.py` | Whether another user is verified, by their latest application; `kyc_latest_status` on Postgres | #230 |
| `invite_to_stokvel`, `accept_stokvel_invitation`, `decline_stokvel_invitation`, `revoke_stokvel_invitation` (routes) | `api/remitx_api/routes/stokvels.py`, `api/remitx_api/routes/stokvel_invitations.py` | The four invitation routes (section 5) | #230, #297 |
| `NotStokvelOrganiserError`, `StokvelDeactivatedError`, `InviteeAccountNotFoundError`, `CannotInviteYourselfError`, `InviteeCurrencyMismatchError`, `InviteeNotKycVerifiedError`, `AlreadyStokvelMemberError`, `InvitationAlreadyPendingError`, `TooManyMembersError`, `InvitationNotFoundError`, `NotInviteeError`, `InvitationNotPendingError`, `KycNotApprovedToJoinStokvelError` | `api/remitx_api/errors/stokvels.py` | The invitation refusals (section 6) | #230 |
| `stokvel_member_can_join`, `kyc_latest_status`, `stokvel_active_member_count` (SQL); triggers `stokvel_member_identity_fixed`, `stokvel_invitation_fixed` | `api/alembic/versions/V20261017_1820__stokvel_member_write_rules.py` | The `stokvel_members` insert rule, the two lookups, the fixed membership identity, and the fixed invitation parties and final answer (section 3) | #230 |
| `open_forming_cycle` | `api/remitx_api/controllers/stokvel_controller.py` | Open a stokvel's cycle 1 as `forming`, with a row for each current member, and make it the current cycle. Used by `create_stokvel` and the setup routes' on-demand path | #231 |
| `StokvelController.create_stokvel` (changed), `StokvelInvitationController.accept` (changed) | `api/remitx_api/controllers/stokvel_controller.py`, `api/remitx_api/controllers/stokvel_invitation_controller.py` | Create also opens cycle 1; accepting adds the member's cycle row while it is `forming` | #231 |
| `StokvelSetupController.set_payout_order`, `.set_beneficiary` | `api/remitx_api/controllers/stokvel_setup_controller.py` | The two R2-09 use cases, each in one transaction under the stokvel row lock. From cycle 2 the order names the members going in; with no forming cycle, the Organiser's call opens the next after a closed one (#237) | #231, #237 |
| `StokvelCycleController.start_cycle` | `api/remitx_api/controllers/stokvel_cycle_controller.py` | Start the forming cycle in one transaction under the stokvel row lock, then queue its registration on-chain | #232 |
| `StokvelCycleRepository.set_round`, `StokvelInvitationRepository.lapse_pending` | `api/remitx_api/repositories/` | Write a round's times in place; lapse a stokvel's pending invitations as the Organiser | #232 |
| `queue_service.enqueue_start_cycle` | `api/remitx_api/services/queue_service.py` | Queue `stokvel.start_cycle` by name (the API and the sweep) | #232 |
| `locked_members_query`, `StokvelCycleRepository.get_locked_members` | `api/remitx_api/repositories/stokvel_cycle_repository.py` | A started cycle's members (its locked rows) in payout order; the one definition the API and the worker share | #232 |
| `stokvel_contract.get_stokvel`, `.create_stokvel`, `.start_cycle` | `api/remitx_worker/stokvel_contract.py` | Read a stokvel on-chain (None if unregistered); send `createStokvel`; send `startCycle` | #232 |
| `StokvelCycleRepository.add_forming_cycle`, `.get_cycle_member`, `.add_cycle_member`, `.clear_payout_positions`, `.pays_beneficiary` | `api/remitx_api/repositories/stokvel_cycle_repository.py` | Add a forming cycle; a member's cycle row; add one; clear every position in a cycle before writing a new order; whether any cycle row pays a beneficiary | #231 |
| `StokvelMemberRepository.list_active` | `api/remitx_api/repositories/stokvel_member_repository.py` | A stokvel's current members, in the order they joined | #231 |
| `set_payout_order`, `set_my_beneficiary` (routes) | `api/remitx_api/routes/stokvels.py` | `PUT /stokvels/{id}/payout-order`, `PUT /stokvels/{id}/members/me/beneficiary` (section 5); schemas `StokvelPayoutOrderRequest`, `StokvelPayoutOrderRead`, `StokvelPayoutPlaceRead`, `StokvelBeneficiaryRequest`, `StokvelBeneficiaryRead` | #231 |
| `PayoutSetupLockedError`, `CycleNotFormingError`, `InvalidPayoutOrderError`; `NotStokvelOrganiserError(action)` (changed) | `api/remitx_api/errors/stokvels.py` | The R2-09 refusals (section 6) | #231 |
| `BeneficiaryInUseError`; `BeneficiaryController.delete` (changed) | `api/remitx_api/errors/beneficiaries.py`, `api/remitx_api/controllers/beneficiary_controller.py` | Refuse to delete a beneficiary a stokvel cycle pays: 409 `beneficiary_in_use_by_stokvel` (section 6) | #231 |
| `STOKVEL_CONTRACT_SUBJECT_ID`; `AuditAction.STOKVEL_CONTRACT_PAUSED`, `.STOKVEL_CONTRACT_UNPAUSED`, `.STOKVEL_ROUND_FINALISED_MANUALLY`; `AuditSubject.STOKVEL`, `.STOKVEL_CONTRACT` | `api/remitx_api/models/orm/audit_log.py` | The stokvel admin-action values. The contract id is fixed because one deployment holds every stokvel (section 5) | #249 |
| `StokvelAdminController.get_contract`, `.list_rounds`, `.finalise_round` | `api/remitx_api/controllers/stokvel_admin_controller.py` | Admin contract read, rounds list, and manual finalise | #247 |
| `read_contract_status`, `list_admin_rounds` | `api/remitx_api/services/stokvel_admin_read.py` | Build admin contract and rounds read models | |
| `StokvelCycleRepository.get_latest_cycle` | `api/remitx_api/repositories/stokvel_cycle_repository.py` | The stokvel's highest-numbered cycle, closed ones included. Also the setup fallback's way to the closed cycle (#237) | #247, #237 |
| `StokvelCycleRepository.get_cycle_by_number` | `api/remitx_api/repositories/stokvel_cycle_repository.py` | A stokvel's cycle by its number, of any status | #237 |
| `open_next_cycle` | `api/remitx_api/controllers/stokvel_cycle_controller.py` | Open the cycle after a closed one as `forming`, under the `stokvels` row lock, with the Organiser's row (beneficiary carried over, closed row `continued`) and rows for members who joined during it. Takes the caller's session: the worker's sync and the setup fallback share it | #237 |
| `going_into` | `api/remitx_api/controllers/stokvel_cycle_controller.py` | The current members who go into a forming cycle: all of them for cycle 1, those with a row in it from cycle 2. Used by the payout order and the start | #237 |
| `StokvelSetupController.continue_or_leave` | `api/remitx_api/controllers/stokvel_setup_controller.py` | Continue (optionally with a new beneficiary) or leave, in one transaction under the stokvel row lock; records `continued` on the closed cycle's row. `_checked_beneficiary` is the beneficiary check it shares with `set_beneficiary` | #237 |
| `StokvelCycleController._end_undecided` | `api/remitx_api/controllers/stokvel_cycle_controller.py` | At the start of cycle 2 onwards, end the membership of closed-cycle members who never chose | #237 |
| `continue_or_leave_stokvel` (route) | `api/remitx_api/routes/stokvels.py` | `POST /stokvels/{id}/members/me/continuation` (section 5); schemas `StokvelContinuationRequest`, `StokvelContinuationRead`; enum `ContinuationChoice` | #237 |
| `NothingToContinueError`, `OrganiserCannotLeaveError`; `InvalidPayoutOrderError.not_continuing`, `.missing_continuing_member` | `api/remitx_api/errors/stokvels.py` | The R2-15 refusals (section 6) | #237 |
| `finalise_readiness`, `classify_finalise`, `FinaliseReadiness` | `api/remitx_api/services/stokvel_contract_read.py` | Read `isFinalisable` and `getCycle` and say whether `finalise` would release, refuse, or finds no open cycle. Fails closed when the vault cannot be read | #247 |
| `RoundNotFinalisableError`, `RoundAlreadyFinalisedError`, `RoundReleaseNotPendingError`, `StokvelChainMismatchError` | `api/remitx_api/errors/stokvels.py` | 409 `round_not_finalisable`, `round_already_finalised`, `round_release_not_pending`; 503 `stokvel_chain_mismatch` (section 6) | #247 |
| `finalise_stokvel_round` (route) | `api/remitx_api/routes/admin/stokvels.py` | `POST /admin/stokvels/{id}/rounds/{n}/finalise`, response `StokvelRoundFinaliseResponse` | #247 |
| `PermissionCode.STOKVEL_ROUND_FINALISE` | `api/remitx_api/models/orm/permission.py` | `stokvel:round:finalise`, granted to the compliance officer | #247 |
| `plan_members`, `refuse_if_already_seeded`, `StokvelDemoStory` | `tools/seeder/remitx_seeder/stories/stokvel.py` | Plan the demo's three members; refuse a second demo on the same database; fund them for every stokvel they are in; set up both stokvels through the stokvel controllers; report an unfinished setup as a refusal | #268 |
| `TransactionRepository.confirmed_net` | `api/remitx_api/repositories/transaction_repository.py` | Confirmed amount into an account minus confirmed amount out, in one currency | #245 |
| `TransactionRepository.in_flight_net` | `api/remitx_api/repositories/transaction_repository.py` | Same net over `processing` legs that already have an `evm_tx_hash`. Not proof the chain moved | #245 |
| `AccountRepository.sum_stokvel_balances` | `api/remitx_api/repositories/account_repository.py` | Token held on every `STOKVEL` account: unreleased pools in the contract | #245 |
| `check_pool_reconciliation` | `api/remitx_api/services/stokvel_reconciliation_service.py` | Compare an on-chain UCTUSD balance with the Treasury float; also return what the contract still holds and the in-flight net | #245 |
| `MoneyStory.deposit_to_keep`, `MoneyStory.recipient_pool`, `MoneyStory.add_beneficiary` | `tools/seeder/remitx_seeder/stories/money.py` | A reconciled deposit with no sends or cash-out; who may become a sender's beneficiary (shared by the money and demo stories); add one and return it | #268 |
| `SeededPerson.scripted`; `clerk.can_sign_in` | `tools/seeder/remitx_seeder/context.py`, `clerk.py` | A person a story owns, whom the engine and other stories leave alone; whether a `clerk_user_id` is a real Clerk account | #268 |
| `stokvelQueries.detail`, `stokvelQueries.list`, `stokvelMutations` | `frontend/app/lib/stokvels.ts` | Member list and detail, and the member writes, through the generated client. `detail` is `GET /stokvels/{id}`. `startCycleBlockers` only knows the caller's `my_beneficiary`. Both queries refetch while the screen is open | #258 |
| `stokvelPollInterval`, `stokvelDetailPollInterval` | `frontend/app/lib/stokvels.ts` | 3 seconds while a stokvel screen has a read to show; 1.5 seconds on a stokvel page while the caller's contribution is pending or processing. A failed first read does not poll | |
| `open_round` on `StokvelDetailRead` | `api/remitx_api/controllers/stokvel_controller.py`, `api/remitx_api/models/schemas/stokvel.py` | The collecting round on `GET /stokvels/{id}`, from `StokvelContributionRepository.open_round`. The member screen reads it. `current_round` stays the stored column | #258 |