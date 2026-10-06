# Stokvel Integration

This file keeps track of the process of implementing the Stokvel integration into the RemitX platform: the features added, how the pieces are connected, the user flow, and the files and functions created along the way. It is the shared contract between the six roles: everything one person builds that another person's code depends on. If someone's Claude session needs a function name, a status value or an API shape, it should come from here, not be invented.

Terminology follows [CONTEXT.md](../CONTEXT.md). Architectural decisions are recorded in [docs/adr/](adr/). The class brief is [ftc_project_brief.md](ftc_project_brief.md).

## Ownership and change rule

| Section | Owner |
|---|---|
| 1. Contract interface | Role 1 |
| 2. Network and addresses | Role 1 |
| 3. Database model | Roles 2 and 3 |
| 4. Worker tasks | Roles 2 and 3 |
| 5. REST API | Roles 2, 3 and 4 |
| 6. Error mapping | Roles 1, 2 and 4 |
| 7. TrustMeBank touchpoints | Role 5 |
| 8. Open questions | All |
| 9–14. Progress, features, flow, files, functions | Whoever makes the change |
| Decisions, Proposals, Deviations, EVM switch-over | All (changes via PR) |

**Change rule:** any change to an interface in this file goes through a PR approved by the owners it affects. No one changes an interface quietly inside a feature PR.

## Changelog

| Date | Section | Change | PR |
|---|---|---|---|
| 2026-10-05 | all | File created with section skeleton | |
| 2026-10-06 | all | Added Decisions, Proposals, Deviations, EVM switch-over, work breakdown; drafted sections 1–8 and 11–12 from CONTEXT.md, GitHub issues #197–#209 and earlier design sessions | |

---

## Decisions (agreed; change only via PR)

| # | Decision | Source |
|---|---|---|
| D1 | The whole system moves from XRPL to the XRPL **EVM** Testnet. No XRPL Testnet code remains. | Design session |
| D2 | One custodial EVM **Treasury Wallet** (the existing term is kept). The database ledger, not separate addresses, tells contribution, pool release and burn movements apart. Whether to add a separate settlement wallet stays open (#207, section 8). | Design session, CONTEXT.md |
| D3 | Users create stokvels and invite other users. The Organiser sets attributes and payout order. The Administrator only has oversight and the global pause. | CONTEXT.md |
| D4 | One contract deployment holds many stokvels (`mapping(stokvelId => Stokvel)`), each with nested cycles and a per-round pool. History is events plus minimal storage (paid, finalised, entitled member). | Design session |
| D5 | Finalise is automatic. Round N releases once every member has contributed to round N+1. The last round of a cycle releases once every member has contributed to it. | CONTEXT.md |
| D6 | The Stokvel is the remittance **sender**. The pool is paid to the scheduled member's Payout beneficiary through the existing remittance flow. Fee and margin are deducted from the pool. | CONTEXT.md |
| D7 | Contributions are paid from the member's fiat account in the Stokvel currency and refunded as the original fiat amount. The deadline is informational only; there are no penalties on the platform. | CONTEXT.md |
| D8 | A Stokvel has no sending limits. Each contribution counts toward the member's own limits. Joining needs the required KYC standing. | CONTEXT.md |
| D9 | The Stokvel gets a ledger `accounts` row of a new type `STOKVEL` (token currency) and is the sender of its payout remittance. | Team, 2026-10-06 |
| D10 | The "hold the payout until the recipient pays the next round" idea is already covered by D5. The CONTEXT.md rule stays. A per-member early release (release as soon as the recipient alone has paid the next round) is not adopted. | Team, 2026-10-06 |
| D11 | The XRPL variables in `.env` (`XRPL_*`, `PLATFORM_WALLET_*`, `UCTUSD_ISSUER*`) are decommissioned, not removed. | Team, 2026-10-06 |

## Proposals for product (status: Proposed)

These come from the dev team and need product approval before they are treated as requirements.

| # | Proposal | Why | Status |
|---|---|---|---|
| P1 | **Users create stokvels and invite other users**, instead of a RemitX admin creating them (brief §2 step 1). | Scales better and removes the admin bottleneck. The admin keeps oversight only. | Proposed |
| P2 | **Payout hold to reduce defaulting after payout.** The contract holds a round's pool until the next round is fully paid, so a member who has already been paid cannot stop contributing without blocking everyone. The final round has no next round, so it pays out once everyone has paid it. | Mitigates the default risk the brief names. It is the same rule as D5. | Proposed, needs legal review |
| P3 | **Member cap of 3 for the prototype, built to grow.** One constant sets the limit: backend `MAX_STOKVEL_MEMBERS`, and a `maxMembers` value in the contract set at deployment. No fixed-size arrays; round counts are `uint8` (up to 255); cycle length equals the number of members. Raising the limit to 10 or 12 (#197) is a config change. | Brief says three members. Building for more costs little now. | Proposed |
| P4 | **Cancellation.** Ending a stokvel, including partway through a cycle, stops future rounds and refunds unfinalised contributions in the original fiat. Possibly admin-only, on request. | Reverses the brief's "refunds out of scope". | Open (#208) |

**Legal questions for product (P2):** is a payout that is conditional on a later contribution permitted under South African consumer-protection law and the stokvel exemption from the Banks Act? Trade-off to note: one late payer delays everyone's payout, because every member must have paid before a round releases.

## Deviations from the brief

The brief (§2, §7, §9) describes one stokvel, three members, an administrator who sets it up and finalises each round, and lists multiple stokvels and refunds as out of scope. This build extends it:

- Many stokvels in one contract, multiple cycles, user-created with invitations (D3, D4, P1).
- Finalisation is automatic, not an administrator action (D5).
- Refunds on mid-round cancellation (P4).
- The XRP Ledger is replaced by the EVM chain (D1).

The final demo must still show everything the brief requires: three synthetic members across three rounds, a round blocked because one member has not paid, and a duplicate contribution and an early finalisation being rejected. If the contract is not deployed and tested by Friday 9 October, reduce scope (drop cancellation and multi-cycle first), as the brief instructs.

---

## 1. Contract interface (Role 1)

> Write first (week-1 deadline). Everything below is a draft until Role 1 confirms it.

### Units and IDs

- Amounts are in UCTUSD's smallest unit (18 decimals).
- Stokvel and member IDs are database UUIDs packed into `bytes32`, left-aligned (the 16 UUID bytes first, the rest zero). Provide one conversion helper in the backend and one in the contract tests so they cannot drift.
- Limits: minimum members 2 (per CONTEXT.md). Maximum is `maxMembers`, set at deployment (3 for the prototype; see P3).
- Contribution amount is a fixed UCTUSD amount, locked at cycle start. The backend converts the Stokvel-currency amount to tokens once, at cycle start.

### Roles (OpenZeppelin AccessControl)

| Role | Held by | Can |
|---|---|---|
| `DEFAULT_ADMIN_ROLE` | Platform owner | Grant roles, pause and resume |
| `OPERATOR_ROLE` | Backend, via the Treasury Wallet | Create stokvels, start cycles, submit contributions, finalise, refund |

The contract relies on the backend to identify the contributing member (brief §7.4); document this in the contract README.

### Functions

| Signature | Caller | Purpose |
|---|---|---|
| `createStokvel(bytes32 id, uint256 contribution)` | Operator | Register a stokvel |
| `startCycle(bytes32 id, bytes32[] memberIds, uint64[] roundStartTimes, uint64[] roundDeadlines)` | Operator | Fix members (payout order = array order) and the schedule for a new cycle |
| `contribute(bytes32 id, uint8 round, bytes32 memberId)` | Operator | Pull `contribution` UCTUSD from the Treasury Wallet and record it against member and round |
| `finalise(bytes32 id, uint8 round)` | Operator | Release the round's pool to the Treasury Wallet and record the entitled member. Reverts unless the release conditions hold |
| `cancel(bytes32 id)` | Operator (admin-requested) | Stop the stokvel; mark contributions to unfinalised rounds refundable |
| `refund(bytes32 id, uint8 round, bytes32 memberId)` | Operator | Return one refundable contribution to the Treasury Wallet |
| `pause()` / `unpause()` | Admin | Halt or resume contributions, finalisation and refunds for every stokvel; never bypasses conditions |

**Automatic finalisation (D5):** when a `contribute` call completes round N+1 (every member has paid it), the same transaction finalises round N. `finalise` remains externally callable so the backend can release the last round, and so the demo can show an early call being rejected. No person triggers it.

Uses OpenZeppelin `AccessControl`, `Pausable`, `ReentrancyGuard` and `SafeERC20`.

### Custom errors

| Error | Raised when |
|---|---|
| `NotMember` | The member ID is not in the stokvel's current cycle |
| `AlreadyPaid` | The member has already contributed to that round |
| `WrongRound` | The round is not currently open for contributions |
| `WrongAmount` | The transferred amount differs from the locked contribution |
| `NotYetFinalisable` | Release conditions are not met (not all members paid the next round, or the last round is not fully paid) |
| `AlreadyFinalised` | The round was already released |
| `CycleClosed` | The cycle ended, or the stokvel was cancelled |
| `UnknownStokvel` | The stokvel ID is not registered |
| `MaxMembersExceeded` | `startCycle` is given more members than `maxMembers` |

Access and pause failures use OpenZeppelin's own errors.

### Events

| Event | Indexed | Other fields |
|---|---|---|
| `ContributionMade(bytes32 indexed id, uint8 round, bytes32 indexed memberId, uint256 amount)` | `id`, `memberId` | `round`, `amount` |
| `RoundFinalised(bytes32 indexed id, uint8 round, bytes32 indexed memberId, uint256 pool)` | `id`, `memberId` | `round`, `pool` |
| `CycleStarted(bytes32 indexed id, uint32 cycle)` | `id` | `cycle` |
| `CycleClosed(bytes32 indexed id, uint32 cycle)` | `id` | `cycle` |
| `StokvelCancelled(bytes32 indexed id)` | `id` | |
| `ContributionRefunded(bytes32 indexed id, uint8 round, bytes32 indexed memberId, uint256 amount)` | `id`, `memberId` | `round`, `amount` |

Events are the history. The contract's storage holds only what rules need: per-round paid flags, per-round pool, finalised flags, the entitled member per round, and the current cycle and round.

### View functions

_TBD (Role 1): names and return values for `getStokvel`, `getCycle`, `hasPaid(id, round, memberId)`, `roundPool(id, round)`, `isFinalisable(id, round)`._

---

## 2. Network and addresses

| Item | Value |
|---|---|
| Network | XRPL EVM Testnet |
| Chain ID | 1449000 |
| RPC URL | `https://rpc.testnet.xrplevm.org` |
| UCTUSD address | `0x7055071C7B79A859d9514e62833BFf041ce71074` (18 decimals) |
| UCTUSD distributor | `0xE054D006c45586251872a7EA17Af40b907745293` |
| Stokvel contract address | _TBD (after deployment)_ |

The sidechain has no trust lines; a wallet address is enough to hold UCTUSD. Test XRP pays gas (faucet: XRPL EVM Testnet).

### Wallet roles (addresses only, never keys)

| Role | Address |
|---|---|
| Deployer | _TBD_ |
| Treasury Wallet (also the contract's operator and release recipient, per D2) | _TBD_ |

### Environment variables

Added to `.env.example` (and `.env.minimal.example` if local dev needs them). They supersede `XRPL_TESTNET_URL`, `XRPL_ENCRYPTION_KEY`, `PLATFORM_WALLET_ADDRESS`, `PLATFORM_WALLET_SEED_ENCRYPTED`, `UCTUSD_ISSUER` and `UCTUSD_ISSUER_LABEL`.

**The XRPL variables are decommissioned, not removed.** Leave them in `.env` and `.env.example` (and in `config.py`), marked as decommissioned with a comment, and make sure no EVM code path reads them. Do not delete them as part of the EVM switch-over.

| Name | Meaning |
|---|---|
| `EVM_RPC_URL` | RPC endpoint |
| `EVM_CHAIN_ID` | 1449000 |
| `UCTUSD_CONTRACT_ADDRESS` | The ERC-20 token |
| `STOKVEL_CONTRACT_ADDRESS` | The stokvel contract |
| `EVM_TREASURY_ADDRESS` | The Treasury Wallet address |
| `EVM_TREASURY_KEY_ENCRYPTED` | Encrypted Treasury Wallet private key; decryption key held outside the database |
| `EVM_ENCRYPTION_KEY` | Fernet key that decrypts it (as `XRPL_ENCRYPTION_KEY` does today) |
| `MAX_STOKVEL_MEMBERS` | Member cap (3 for the prototype; see P3) |

Keys never appear in the frontend, API responses, logs or git.

---

## 3. Database model (Roles 2 and 3)

> Write first (week-1 deadline). The most important section: backend, frontend and tests all depend on it. Draft; each table needs an ORM model imported in `models/orm/__init__.py`, an Alembic migration, and a row-level-security decision like the ledger tables.

### Tables

| Table | Key columns | Migration |
|---|---|---|
| `stokvels` | `id`, `organiser_user_id`, `name`, `currency` (Stokvel currency), `contribution_amount`, `max_members` (default from config), `status` (`draft`, `active`, `cancelled`), `current_cycle_id`, `account_id` (its `STOKVEL` ledger account), `created_at` | |
| `stokvel_cycles` | `id`, `stokvel_id`, `cycle_number`, `status` (`forming`, `active`, `closed`), `current_round`, `round_count`, `token_contribution_amount` (locked at start), `started_at`, `closed_at` | |
| `stokvel_rounds` | `cycle_id`, `round`, `start_time`, `deadline` | |
| `stokvel_members` | `id`, `stokvel_id`, `user_id`, `joined_at`, `left_at`, `status` (membership across cycles) | |
| `stokvel_cycle_members` | `cycle_id`, `member_id`, `payout_position`, `payout_beneficiary_id`, `payout_currency`, `continued`, `locked` (per-cycle order and beneficiary, locked once the cycle starts) | |
| `stokvel_invitations` | `id`, `stokvel_id`, `invitee_user_id`, `status` (`pending`, `accepted`, `declined`, `lapsed`), `created_at`, `responded_at` | |
| `stokvel_contributions` | `id`, `cycle_id`, `round`, `member_id`, `amount_fiat`, `amount_token`, `tx_id` (ledger), `onchain_tx_hash`, `block_number`, `status`; UNIQUE (`cycle_id`, `round`, `member_id`) | |
| `stokvel_payouts` | `id`, `cycle_id`, `round`, `member_id`, `release_status`, `quote_id`, `remittance_id`, `release_tx_hash`, `burn_tx_hash`; UNIQUE (`cycle_id`, `round`) | |

Differences from the first sketch (a `stokvel` table plus a `stokvel_member` table):

- "Contributed this month or not" is **derived** from `stokvel_contributions`, not stored. A flag would go stale. A round is a contribution period set by the Organiser, not a calendar month.
- `number_of_members` is derived from members and capped by `max_members`.
- Cycles, per-cycle payout order and the locked beneficiary need their own tables because membership and beneficiary can change between cycles but are fixed within one.
- `current_round` and `current_cycle_id` are kept as columns for cheap reads.

### Ledger changes

| Change | Detail |
|---|---|
| New account type | `STOKVEL` (currency: the token). Update the `accounts_type_valid` CHECK, and relax `accounts_owner_matches_type` and `accounts_reference_matches_type` for it (no user, no reference). One per stokvel. |
| New transaction types | `stokvel_contribution` (member fiat account → platform bank, then token legs into the stokvel account), `stokvel_pool_release` (contract → Treasury Wallet → stokvel account), `stokvel_refund`. Update `transactions_type_valid` (precedent: `V20260921_1400__add_burn_and_payout_transaction_types.py`). |
| Payout legs | Reuse the existing `remittance`, `fee`, `token_burn` and `beneficiary_payout` legs grouped by `quote_id`, with the stokvel account as sender, so the proven settlement worker and its idempotency are reused. A separate `STOKVEL_REMITTANCE` type was suggested; see section 8. |
| Quote sender | `quotes.sender_user_id` is NOT NULL today. Make it nullable and add `stokvel_id` (or `sender_account_id`). Stokvel quotes skip `require_can_send` (D8). |
| Chain-neutral names | `transactions.xrpl_tx_hash` → `onchain_tx_hash`; account type `REMITX_XRPL_WALLET` → `REMITX_EVM_WALLET`; seeded label "RemitX XRPL Treasury Wallet" → "RemitX Treasury Wallet" (also in `remittance_service.py`; the two must match). |
| Limits | Contributions count toward the member's limits: extend `RemittanceRepository.sent_zar` (or add a parallel sum) so contributions are included. |

### Status values and transitions

| Entity | Transitions |
|---|---|
| Contribution | `pending → processing → confirmed \| failed` |
| Pool release | `pending → processing → released \| failed` |
| Remittance | `pending → processing → confirmed \| failed` (the existing transaction states; `created`, `burning`, `burnt` and `credited` are not separate states) |
| Invitation | `pending → accepted \| declined \| lapsed` |
| Cycle | `forming → active → closed` |

_The brief's wording of the remittance statuses (`created → burning → burnt → credited`) differs from the existing ledger states; confirm with Role 2/3 before the frontend depends on either._

### Where on-chain values are stored

| Value | Column |
|---|---|
| Contribution transaction hash | `stokvel_contributions.onchain_tx_hash` |
| Pool release hash | `stokvel_payouts.release_tx_hash` |
| Burn hash | `transactions.onchain_tx_hash` (on the `token_burn` leg) and `stokvel_payouts.burn_tx_hash` |
| Remittance reference | `stokvel_payouts.remittance_id` (→ `remittances`) |
| Block number | `stokvel_contributions.block_number` |

### Idempotency rules

| Step | What stops it running twice |
|---|---|
| Submit contribution | UNIQUE (`cycle_id`, `round`, `member_id`); guarded `pending → processing` claim in the worker; contract `AlreadyPaid` |
| Release pool | UNIQUE (`cycle_id`, `round`) on `stokvel_payouts`; guarded `pending → processing` claim; contract `AlreadyFinalised` |
| Credit remittance | Existing guarded group-confirm on `quote_id` (`confirm_treasury_burn`); a retry must not repeat the release, burn or credit |
| Refund | Guarded status transition on the contribution; contract refund-once flag |

---

## 4. Worker tasks (Roles 2 and 3)

Celery tasks, queued by name over the broker (the API never imports `remitx_worker`). As in the existing settlement path, the task that makes the network call is separate from the task that records the result in the database, so the database step can be retried on its own.

| Task | Payload | Queued by | Retry behaviour |
|---|---|---|---|
| `stokvel.submit_contribution` | `contribution_id` | API on `POST /stokvels/{id}/contributions` | Claim `pending → processing`; a redelivery is a no-op; broker retry on RPC error |
| `stokvel.confirm_contribution` | `contribution_id`, `tx_hash`, `error` | `submit_contribution` | DB-only; safe to retry |
| `stokvel.release_pool` | `payout_id` | `confirm_contribution` when a round becomes releasable, and for the last round | Claim guard; contract rejects a second release |
| `stokvel.settle_payout` | `payout_id` | `release_pool` on success | Creates the stokvel-sender quote and remittance, then hands to the existing `settle_remittance` / burn chain |
| `stokvel.sync_events` | none (beat) | Celery beat | Reads contract logs from the last processed block; updates the database idempotently |
| `stokvel.refund` | `contribution_id` | Cancellation | Claim guard; refund original fiat to the source account |

### Contract event → database update

| Event | Effect |
|---|---|
| `ContributionMade` | Mark the contribution `confirmed`, store hash and block |
| `RoundFinalised` | Mark the payout `released`, trigger `stokvel.settle_payout` |
| `CycleClosed` | Close the cycle; open the continuation choice for members |
| `StokvelCancelled` / `ContributionRefunded` | Mark the stokvel `cancelled`; queue refunds |

---

## 5. REST API (Roles 2, 3 and 4)

> Write first (week-1 deadline). Once routes exist, `frontend/openapi.json` is the source of truth for exact fields; this section only agrees shapes beforehand. Each route needs a `summary=`, `responses=error_responses(...)` and a dotted `Tag` (`stokvels`, `admin.stokvels`); run `python scripts/export_openapi.py` afterwards.

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /stokvels` | Authenticated user (KYC standing) | Create a stokvel |
| `GET /stokvels` | Authenticated user | List the caller's stokvels and pending invitations |
| `POST /stokvels/{id}/invitations` | Organiser | Invite a user |
| `POST /invitations/{id}/accept` | Invitee | Accept an invitation |
| `POST /invitations/{id}/decline` | Invitee | Decline an invitation |
| `PUT /stokvels/{id}/payout-order` | Organiser | Set the payout order before a cycle |
| `PUT /stokvels/{id}/members/me/beneficiary` | Member | Choose beneficiary and payout currency for the next cycle |
| `POST /stokvels/{id}/cycles` | Organiser | Start a cycle (needs at least 2 ready members, every one with a beneficiary) |
| `POST /stokvels/{id}/members/me/continuation` | Member | Continue or leave after a cycle ends |
| `POST /stokvels/{id}/contributions` | Member | Contribute to the current round |
| `GET /stokvels/{id}` | Member | Member screen data: group, amount, schedule, order, paid and outstanding, round and payout status, hashes, remittance references |
| `POST /admin/stokvel-contract/pause` and `/unpause` | Administrator | Emergency stop and resume |
| `POST /admin/stokvels/{id}/cancel` | Administrator | Cancel (if P4 is approved) |

Removed from the earlier idea: `POST /admin/stokvels/{id}/rounds/{n}/finalise`. Finalisation is automatic (D5).

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
| `CycleClosed` | 409 `cycle_closed` | "This cycle has ended." |
| `MaxMembersExceeded` | 422 `too_many_members` | "A stokvel can have at most {max} members." |
| OpenZeppelin `EnforcedPause` | 503 `stokvel_paused` | "Stokvels are temporarily paused." |

_Roles 1, 2 and 4 to confirm codes and wording._

---

## 7. TrustMeBank touchpoints (Role 5)

TrustMeBank is an optional extension in the brief. It provides the fiat in and out: deposits authorised through TrustMeBank (#202) and withdrawals paid out through it (#203). It replaces CSV reconciliation as an additional path. Stokvel contributions draw from the member's existing fiat account, so the stokvel path does not depend on it.

- Webhook endpoint: _TBD_
- Events handled: _TBD_
- Deposit statuses: _TBD_
- How a completed payment links to a deposit record: _TBD_

Today TrustMeBank exists only in documents; the code reconciles CSV statements in `services/deposit_service.py`.

---

## 8. Open questions

| Question | Status | Owner | ADR |
|---|---|---|---|
| One Treasury Wallet, or a separate settlement wallet for pool release (#207)? D2 chooses one wallet; confirm | Open | Role 1 | |
| Burn method (#206): does UCTUSD have a `burn()` function, or do we transfer to a dead address? Check the token on the explorer | Open | Role 1 | |
| Contribution is a fixed token amount locked at cycle start, but members pay in fiat and rates move. Proposal: member debit = token amount × live rate at contribution; refunds return the original fiat | Open | Roles 2, 3 | |
| New `STOKVEL_REMITTANCE` type, or reuse the existing remittance legs with the stokvel account as sender (this doc's recommendation)? | Open | Roles 2, 3 | |
| Cancellation (P4): who may cancel, and does it reverse the brief's "refunds out of scope"? (#208) | Open | Product | |
| Are fees taken out of the pool? CONTEXT.md says yes (D6) | Confirm | Product | |
| Legal status of P2 (payout conditional on the next contribution) | Open | Product | |
| Remittance status names: brief's `created → burning → burnt → credited` vs existing ledger states | Open | Roles 2, 3 | |
| Row-level security for the new stokvel tables | Open | Roles 2, 3 | |
| Seeder and load test: update stories and `tools/loadtest/fake_xrpl_worker.py` for EVM | Open | Role 6 | |

Resolved: the finalise endpoint idea was dropped; finalisation is automatic (D5).

---

## 9. Implementation progress

Milestones (Katlego-Sekoele/RemitX): *EVM wallet setup and switch over*, *Bank API Integration and Bank Deposit simulation switch over*, *Smart Contract Creation and Connection*.

| Step | Status | Issues | Notes |
|---|---|---|---|
| Replace the XRPL layer with EVM | Not started | #204 | See "EVM switch-over" below |
| Treasury Wallet as EVM address, encrypted key | Not started | #205 | |
| Burn UCTUSD on EVM | Not started | #206 | Needs burn-method answer |
| Contract: stokvels and cycles | Not started | #197 | |
| Contract: contributions and finalisation | Not started | #198 | |
| Contract: pause and resume | Not started | #199 | |
| Contract tests and testnet deployment | Not started | #200 | Brief deadline: Fri 9 Oct |
| Backend connection to the contract | Not started | #201 | |
| Members create stokvels and invite others | Not started | #209 | |
| DB models and migrations | Not started | | Section 3 |
| Worker tasks | Not started | | Section 4 |
| API routes | Not started | | Section 5 |
| Frontend screens | Not started | | Member, Organiser, invitations, admin pause |
| TrustMeBank deposits and withdrawals | Not started | #202, #203 | |
| Stokvel cancellation | Not started | #208 | Open question |

### Brief timeline

| Date | Target |
|---|---|
| Fri 9 Oct | Contract deployed and tested; backend can submit a contribution and read state |
| Fri 16 Oct | One full round end to end; member and admin screens |
| Fri 23 Oct | All three rounds on the deployed version, plus blocked round and rejected duplicate and early finalisation; settlement retry test passes; code freeze and tag |
| Mon 26 – Wed 28 Oct | Rehearsal, backup video, submission, presentation |

### Work breakdown

1. **EVM switch-over** (#204–#206): see the list below.
2. **Contract** (#197–#200): Hardhat or Foundry project in `contracts/`, tests per brief §7.5, deploy and record the address in section 2.
3. **Backend stokvel domain**: models and migrations → repositories → controllers → thin routes. Copy the shape of `confirm_remittance` for contributions: lock the user, check standing and limits, check available balance, insert pending legs sharing a group id.
4. **Settlement** (#201): contribution submit and confirm, event sync, pool release → stokvel account → remittance → existing burn chain. A retried settlement must not duplicate release, burn or credit.
5. **Frontend**: member and Organiser screens, invitations, admin pause and cancel, using shadcn/ui and Aceternity per CLAUDE.md; run `npm run generate:api`.
6. **Testing and demo**: three members × three rounds, blocked round, duplicate contribution, early finalisation, settlement retry test, seeder story updates.

### EVM switch-over: what changes

| Area | Change |
|---|---|
| `api/remitx_worker/xrpl_service.py` | Replace with an `evm_service.py` using web3.py: load and decrypt the Treasury key, send transactions, wait for receipts, call the burn. The XRPL `Payment` to the issuer goes away |
| `platform_wallet/scripts/create_xprl_platform_wallet.py` | Rewrite: generate an EVM key, Fernet-encrypt it into `.env`, no faucet wallet or trust line |
| `api/pyproject.toml` | Swap `xrpl-py` for `web3` |
| `config.py`, `.env.example`, `.env.minimal.example` | New `EVM_*` variables (section 2). Keep `XRPL_*`, `PLATFORM_WALLET_*` and `UCTUSD_ISSUER*` in place, marked decommissioned and unused by EVM code; do not remove them |
| Migration | Rename `xrpl_tx_hash`, the `REMITX_XRPL_WALLET` type and CHECK, and the seeded wallet label; add `STOKVEL` and the new transaction types |
| `services/transfer_timeline.py`, `controllers/remittance_controller.py`, settlement-recovery code | Replace "Settling on XRPL Testnet / RLUSD" text and the `xrpl_tx_hash` field |
| `remitx_worker/tasks.py` | Burn and confirm tasks keep their shape; call `evm_service` |
| Tests | Worker burn tests mock `xrpl_service`: repoint at `evm_service` |
| `tools/seeder`, `tools/loadtest/fake_xrpl_worker.py` | Update for EVM |
| Docs | [CLAUDE.md](../CLAUDE.md) (hard constraint says "XRPL Testnet only"; RLUSD wording), [Transaction_Flow_Context.md](Transaction_Flow_Context.md), [DEPLOYMENT.md](DEPLOYMENT.md), `project-brief.md`; add ADRs for single contract with many stokvels, the `STOKVEL` ledger account, and the single Treasury Wallet; add "Cancellation" to CONTEXT.md if P4 is approved |

## 10. Features added

_Add one entry per feature as it lands: what it does, who owns it, PR link._

## 11. How things are connected

```
Frontend → API route → controller → ledger legs (pending) → queue
       → worker (web3.py) → stokvel contract → event → sync task → database
```

- **Contribution:** the member's fiat account is debited (counts toward their limits), the platform converts the amount to UCTUSD, and the worker sends it from the Treasury Wallet to the contract with `contribute`. The contribution is `confirmed` only after the on-chain event.
- **Finalisation:** when every member has paid round N+1 (or everyone has paid the last round), the contract releases round N's pool to the Treasury Wallet. The database credits the stokvel's `STOKVEL` ledger account.
- **Payout:** the stokvel is the sender. A quote and remittance are created from the stokvel account to the scheduled member's Payout beneficiary, using FSE's fee and margin, deducted from the pool. The existing settlement chain burns the UCTUSD and credits the beneficiary's payout-currency account. The burn hash, beneficiary credit and remittance reference are stored together.
- **No bridge:** nothing moves on the XRP Ledger; the remittance step produces the quotation, record and reference, and the burn stands for the simulated cash-out.

## 12. User flow

1. A KYC-approved user creates a stokvel (name, Stokvel currency, contribution, start time, deadlines).
2. The Organiser invites users by account reference. Only KYC-approved users with a fiat account in the Stokvel currency can be invited. Nobody is a member until they accept.
3. The Organiser sets the payout order.
4. Each member chooses a Payout beneficiary and payout currency (the account must already exist).
5. The Organiser starts the cycle once at least two members are ready. Invitations not yet accepted lapse. Membership, order and beneficiaries are now locked.
6. Each round, every member contributes before the deadline (informational only).
7. The contract finalises automatically; the payout remittance goes to the scheduled member's beneficiary; the member sees status, hashes and the remittance reference.
8. After the last round the cycle closes. Each member chooses to continue or leave, and may change their beneficiary; a new cycle can then start.

## 13. Files created

| File | Purpose | Added in |
|---|---|---|
| `docs/stokvel_integration.md` | This tracking document | |

## 14. Functions created

| Function | File | Purpose | Added in |
|---|---|---|---|
| | | | |
