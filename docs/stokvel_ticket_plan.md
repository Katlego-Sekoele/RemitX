# Stokvel ticket plan

Draft for the team. The tickets were created on GitHub on 2026-10-07 (see "GitHub issues" at the bottom). If the plan and an issue disagree, tell the plan's owner and update both. Sources: [ftc_project_brief.md](ftc_project_brief.md) (graded), [stokvel_integration.md](stokvel_integration.md) (shared contract), and the open issues #197–#209 on Katlego-Sekoele/RemitX (bodies read).

## How the tickets are written

- **One owner per ticket**, named in the ticket. A second person is listed only as "supports".
- **Size:** S ≈ half a day, M ≈ one day, L ≈ two days. Nothing is bigger than L; anything larger was split.
- **Every ticket has a task checklist** (GitHub task list), so progress shows on the issue and work can be handed over mid-ticket.
- **Type:** *core* (the brief requires it or the demo needs it) or *extension* (beyond the brief; first to cut).
- **Refs:** the brief section and the integration-doc section the ticket implements. Names, statuses and API shapes come from the doc, not from the ticket.
- **Files:** the files each ticket will likely create, change or delete, taken from the current layout of the repo. **These lists are suggestions only, to help implementation.** They are not requirements: the owner may use different files or names, and should confirm or adjust them at the start. A ticket's tests, `frontend/openapi.json` regeneration and `docs/stokvel_integration.md` updates (changelog row, new functions and files) are expected on top of this list. `contracts/` does not exist in this repo yet.

## Where the brief and the doc differ

These were found while checking tickets against the brief. They are settled by ticket D1 or D4, not silently in a feature ticket.

| # | Brief | This build (doc) | What to do |
|---|---|---|---|
| 1 | §9 out of scope: refunds, multiple stokvels, automated scheduling | Doc extends: many stokvels in one contract (D4), user-created with invitations (D3), cancel and refund (P4), repeat cycles | The brief's core path is built first. Cancel, refund and repeat cycles are *extension* tickets in their own milestone |
| 2 | §7.1: finalise only when all have paid **and the payout time has passed** | D5 and D12: round N releases once every member has paid round N+1 **and** its Organiser-set payout time has passed. The contribution deadline stays informational. A blocked round stays blocked until the last member pays | Decided (2026-10-07). D1 writes it into doc §1. A scheduled task (R3-11) releases rounds that are due. Product is asked whether to merge deadline and payout time (P6) |
| 3 | §2 step 4: the administrator finalises each round | D5: automatic by default. `finalise` stays externally callable, and the Administrator can trigger it manually as a fallback (P5) | Recorded deviation. R1 tests the early call. Manual admin finalise is R3-10 and R4-11 (pending product approval of P5) |
| 4 | §7.3 admin screen: finalise rounds, pause, resume | Finalise (fallback), pause and resume | Admin screen has all three if P5 is approved; otherwise pause and resume only. A blocked finalisation is shown by clicking Finalise on a round that is not ready |
| 5 | §7.3: reuse FSE's existing beneficiary screen (the contact list) | Beneficiary and payout-currency choice per member | The picker selects an existing beneficiary; it does not rebuild the add-beneficiary form |
| 6 | §7.2: statuses `created → burning → burnt → credited` | Ledger uses `pending → processing → confirmed \| failed` | Recommendation: keep the ledger states (the ledger already uses them; the brief's names would need several changes). Product confirms; D4 records it before the frontend depends on either |
| 7 | Three members | #197 and #209 say cap 12; doc P3 says 3, built to grow | D3 decides: one config value, 3 for the prototype |
| 8 | Admin sets up the stokvel; "a script is acceptable" | Users create stokvels and invite others | Kept (agreed D3), but the setup API is only as large as it needs to be |
| 9 | §7.2: no RLUSD moves on XRPL; the burn is the simulated cash-out | #207 wording "pays the beneficiary" could read as a real transfer | Corrected in #207: the pool never moves to a member on-chain |
| 10 | #209: "starts only once everyone has accepted" | CONTEXT.md and doc §12: unaccepted invitations **lapse when the Organiser starts the cycle** (decided) | #209 text is fixed. The start-cycle ticket enforces the doc's rule |

## People

| Person | Role | GitHub | Approx. core load |
|---|---|---|---|
| Kerry | 1 Smart contract | kerryw33 | ~7.5 days (includes R2-12, R2-13 moved from Claire) |
| Claire | 2 Chain integration (backend lead) | clair3campb3ll (to confirm) | ~10 days (down from ~13 after moving R2-05, R2-06, R2-12, R2-13; includes R2-03 moved from Katlego) |
| Sian | 3 Settlement and payout | SianC7 | ~7.5 days (R3-07, R3-08, R3-10, R3-12 moved to Katlego; supports Claire on R2-03) |
| Karabo | 4 Frontend | Karabo22Tigedi | ~9.5 days |
| Katlego | 5 Fiat, deploy, security | Katlego-Sekoele | ~5.5 days (includes R3-07, R3-08, R3-10, R3-12 moved from Sian; R2-03 moved to Claire), plus #202 and #203 (now core, ~4 days: ~9.5 days in total) |
| Mridula | 6 Testing and demo | mridulak25 | ~9.5 days (includes R2-05, R2-06 moved from Claire); supports Kerry and Karabo |

## Milestones

Five exist. Two are empty and are reused for the frontend. Four are new.

| Milestone | Status | Holds | Proposed due |
|---|---|---|---|
| Smart Contract Creation and Connection | exists | Contract, deploy, contract tests, interface decisions | Fri 9 Oct |
| EVM wallet setup and switch over | exists | Treasury Wallet, evm_service, XRPL removal, burn | Fri 9 Oct |
| Stokvel Backend Domain | **new** | Tables, ledger changes, member and organiser API, contribution flow, event sync | Fri 16 Oct |
| Settlement and Payout | **new** | Pool release, payout remittance, reconciliation, admin pause route | Fri 16 Oct (one round), Fri 23 Oct (all) |
| Finished Frontend Screens | exists (empty) | Screens on mocked data | Fri 16 Oct |
| Connect Frontend to Backend | exists (empty) | Screens wired to real routes, client regenerated | Fri 23 Oct |
| Testing, Security and Demo | **new** | CI, security checklist, seeder, end-to-end and retry tests, demo | Fri 23 Oct (freeze); demo Wed 28 Oct |
| Bank API Integration and Bank Deposit simulation switch over | exists | #202, #203 (optional in the brief, but required in this build) | Fri 16 Oct |
| Extensions Beyond the Brief | **new** | Cancel, refund, repeat cycles | none; start only after Fri 16 Oct if one round works end to end |

## Edits to existing tickets

| Issue | Owner | Milestone | Change |
|---|---|---|---|
| #197, #198 | Kerry | (closed) | No edit. D1 reconciles them with the doc |
| #199 pause and resume | Kerry | Contract | Contract only. Move the backend route to R3-07 and the admin control to R4-07. Keep the acceptance boxes for the contract |
| #200 tests and deployment | Kerry (Mridula supports) | Contract | Tests only, per brief §7.5. Move deployment to R1-04. Move the cancellation test to R1-06 |
| #201 backend connection | Claire | Stokvel Backend Domain | Convert to an epic. Task list links R2-09 to R2-15 and R3-03 to R3-05. Remove the stale "quote-sender shape" question: D9 decided a `STOKVEL` account |
| #202 TrustMeBank deposits | Katlego | Bank API | Add the task list and an `ENABLE_TRUSTMEBANK` flag. Add a task to fill doc §7. Size L, core (no longer optional) |
| #203 TrustMeBank withdrawals | Katlego | Bank API | Add the task list. Decision already made in the issue: Option B first. Size L, core (no longer optional). Depends on #202 |
| #204 replace XRPL with EVM | Claire | EVM | Convert to an epic with the child tickets R2-01 to R2-04 and #206. Lecturer approval (D2) is received (Marc, 2026-10-07): record it in the issue. Remove "keep the XRPL path until tests pass": D1 and D11 say no XRPL code path remains, only the decommissioned settings |
| #205 Treasury Wallet and key | Claire | EVM | **Key storage changes: the encrypted private key lives in `.env` (`EVM_TREASURY_KEY_ENCRYPTED`, Fernet-encrypted, as the XRPL wallet seed does today), not in a database column.** Drop "stored encrypted in the database" and the DB-row example. Remove the gitleaks rule and the no-leak tests: they move to R5-03 (Katlego owns hardening; Claire already did both in PR #211, open). Funding and the UCTUSD request move to R2-02b. PR #211 (open) covers the wallet script, key loader, redaction, gitleaks rule and leak tests; the operator role at deployment (#200) and UCTUSD funding are still open |
| #206 EVM burn | Sian | EVM | Add the task list. Depends on R1-05 (burn method). Repoint the worker burn tests from `xrpl_service` to `evm_service` |
| #207 settlement wallet | Sian | EVM | Close with an ADR: Option A matches D2. Move the reconciliation check to R3-06 and the security note to R5-03. Correct the "pays the beneficiary" wording |
| #208 cancellation decision | Sian (decider: product) | Extensions | Move to Extensions. State a deadline: Fri 9 Oct, before R1-06 is built |
| #209 create stokvel | Claire | Stokvel Backend Domain | Narrow to "create and list stokvels" (API only). Invitations go to R2-08, the frontend to R4-03 and R4-04. Fix the lapse rule. Fix the cap to config (D3). Tables go to R2-05 |

### Files for the existing issues

_Suggestions only, to help implementation._

| Issue | Files |
|---|---|
| #197, #198 | None (closed). The contract lives in `contracts/`; see R1-01 and D1 |
| #199 | `contracts/src/Stokvel.sol`, `contracts/test/` |
| #200 | `contracts/test/` (deployment moves to R1-04) |
| #201 (epic) | None. Links its child tickets; `docs/stokvel_integration.md` (§9) |
| #202 | `api/remitx_api/services/deposit_service.py`, `controllers/deposit_controller.py`, `routes/admin/deposits.py`, `models/orm/deposit.py` and a migration, `config.py` (`ENABLE_TRUSTMEBANK`), `.env.example`, `api/tests/test_deposit_service.py`, `test_deposits_route.py`, `frontend/app/routes/admin/process-deposits.tsx`, `docs/stokvel_integration.md` (§7) |
| #203 | `api/remitx_api/services/withdrawal_service.py`, `controllers/withdrawal_controller.py`, `routes/admin/withdrawals.py`, `models/orm/withdrawal.py` and a migration, `api/tests/test_withdrawals_route.py`, `frontend/app/lib/withdrawals.ts`, `frontend/app/routes/app/withdraw.tsx` |
| #204 (epic) | None. Links R2-01 to R2-04 and #206 |
| #205 | `platform_wallet/scripts/`, `api/remitx_api/config.py`, `.env.example`, `docs/stokvel_integration.md` (§2). The gitleaks rule and leak tests move to R5-03 |
| #206 | `api/remitx_worker/evm_service.py` (burn), `api/remitx_worker/tasks.py` (`burn_treasury_tokens`), `api/tests/test_worker_burn_treasury_tokens.py` |
| #207 | `docs/adr/NNNN-single-treasury-wallet.md` |
| #208 | `docs/stokvel_integration.md` (P4), `CONTEXT.md` ("Cancellation", if approved) |
| #209 | As R2-07 |

## New tickets

Tickets are listed in ID order within each role; extension tickets are marked in their Type. "Supports" means helps but does not own.

---

### Decisions

#### D1. Reconcile the contract interface between the issues, the doc and the brief
**Owner:** Kerry · **Milestone:** Smart Contract Creation and Connection · **Size:** S · **Type:** core · **Refs:** brief §7.1; doc §1, "Where the brief and the doc differ" #2, #3
**Why:** #197, #198 and doc §1 describe different functions and events, and the backend is about to code against them.
- [ ] Compare #197 and #198 with doc §1: `createStokvel` shape, `startCycle`, event names (`StokvelClosed` vs `CycleClosed`, `recipientId` vs `memberId`).
- [ ] Implement the decided rule (doc D5, D12): `finalise` requires the paid condition **and** `block.timestamp >= payoutTimes[round]`; add `payoutTimes` to `startCycle`; add the "too early" case to `NotYetFinalisable`.
- [ ] Update doc §1 so it matches the contract as built; update the closed issues with a comment linking it.
- [ ] Tell Claire and Sian in the check-in once §1 is stable.
**Files:**
- Change: `docs/stokvel_integration.md` (§1), `contracts/src/Stokvel.sol`
- No other code. Comment on the closed issues #197 and #198 (GitHub).
**Done when:** doc §1 has no TBD or conflict with the contract, and the payout-time rule matches D12.

#### D2. Lecturer approval for moving XRPL to EVM
**Status:** done. Marc approved the move on 2026-10-07; record it in #204.
**Owner:** Sian · **Milestone:** EVM wallet setup and switch over · **Size:** S · **Type:** core · **Refs:** #204
**Why:** the FSE brief required XRPL; every EVM ticket is blocked until this is answered.
- [x] Ask Marc at the Friday 11:00 tech check-in, or by email.
- [ ] Record the answer in #204.
**Files:**
- None. Approval is recorded as a comment on #204 (GitHub).
**Done when:** the approval (or refusal, with the fallback) is in #204.

#### D3. Decide the member cap
**Owner:** Kerry (with Claire) · **Milestone:** Smart Contract Creation and Connection · **Size:** S · **Type:** core · **Refs:** doc P3; brief §2 (three members)
- [ ] Agree: contract `maxMembers` set at deployment, backend `MAX_STOKVEL_MEMBERS`, value 3 for the prototype.
- [ ] Update #197, #209 and doc P3 to the same wording.
**Files:**
- Change: `docs/stokvel_integration.md` (P3), `api/remitx_api/config.py` (`MAX_STOKVEL_MEMBERS`), `.env.example`, contracts deploy script (`maxMembers` argument)
**Done when:** one number lives in one config value on each side, and no ticket says 12.

#### D4. Decide the contribution amount rule and the remittance status names
**Owner:** Sian (with Claire) · **Milestone:** Stokvel Backend Domain · **Size:** S · **Type:** core · **Refs:** brief §7.2; doc §3, §8
- [ ] Contribution amount (product to confirm): fixed token amount or fixed fiat amount? If a fixed token amount, debit = token amount × live rate at contribution; refunds return the original fiat amount entered.
- [ ] Decide the remittance status names the frontend will show (brief `created → burning → burnt → credited` vs the ledger's `pending → processing → confirmed | failed`). Recommendation: the ledger's, pending product confirmation.
- [ ] Record both in doc §3 and §8.
**Files:**
- Change: `docs/stokvel_integration.md` (§3, §8), `api/remitx_api/services/transfer_timeline.py` and `frontend/app/lib/transfer-status.ts` (only if the status names change)
**Done when:** doc §3 states one status set and one rate rule.

---

### Role 1: Smart contract (Kerry; Mridula supports)

#### R1-01. Contract view functions
**Owner:** Kerry · **Milestone:** Smart Contract Creation and Connection · **Size:** S · **Type:** core · **Depends on:** D1 · **Refs:** doc §1
- [ ] Add `getStokvel`, `getCycle`, `hasPaid`, `roundPool`, `isFinalisable`.
- [ ] One test each; `isFinalisable` covers both the paid condition and the payout time.
- [ ] Write their signatures into doc §1.
**Files:**
- Change: `contracts/src/Stokvel.sol`, `contracts/test/` (one test per view), `docs/stokvel_integration.md` (§1)
**Done when:** the backend can read paid state, pool and finalisable state with these calls.

#### R1-02. Contract tests (existing #200, narrowed)
See "Edits": tests only. Owner Kerry, supports Mridula (writes the duplicate, unknown-member and unauthorised-sender tests). Adds tests: finalise rejected before the payout time even when all have paid; round blocked after the payout time while a member has not paid, then released once they pay. Size L. Milestone Smart Contract Creation and Connection.
**Files:**
- Create: `contracts/test/Stokvel.test.*` (framework per the contracts project), `contracts/src/mocks/MockUCTUSD.sol` (test token)
- Change: `contracts/package.json` or `foundry.toml`
- `contracts/` does not exist in this repo yet; confirm where the contract project lives before this ticket starts.

#### R1-03. Pause and resume (existing #199, narrowed)
See "Edits": contract only. Owner Kerry. Size S.
**Files:**
- Change: `contracts/src/Stokvel.sol` (`pause`, `unpause`), `contracts/test/`

#### R1-04. Deploy to the XRPL EVM Testnet
**Owner:** Kerry · **Milestone:** Smart Contract Creation and Connection · **Size:** M · **Type:** core · **Depends on:** #200, #205 (Treasury address) · **Refs:** brief §7.1, §8; doc §2
- [ ] Deployment script reads the deployer key from the environment only.
- [ ] Deployer is a separate address from the Treasury Wallet, funded with test XRP in R2-02b (faucet, Testnet); its key stays in your local `.env`, never committed.
- [ ] Deploy with the UCTUSD address from brief §8; grant the operator role to the Treasury Wallet; admin role stays with the deployer.
- [ ] Verify the contract on the explorer.
- [ ] Record the contract address in doc §2 and `.env.example` (`STOKVEL_CONTRACT_ADDRESS`).
**Files:**
- Create: `contracts/scripts/deploy.*` (reads the deployer key from the environment), `contracts/deployments/xrpl-evm-testnet.json` (address and block)
- Change: `docs/stokvel_integration.md` (§2), `.env.example` (`STOKVEL_CONTRACT_ADDRESS`)
**Done when:** a `contribute` call from the Treasury Wallet succeeds on testnet and the address is in the doc.

#### R1-05. Contract README, ABI export and ADR
**Owner:** Kerry · **Milestone:** Smart Contract Creation and Connection · **Size:** S · **Type:** core · **Refs:** brief §7.4; doc §1
- [ ] State that the contract trusts the backend to identify the contributing member (brief §7.4).
- [ ] Export the ABI to a path the backend reads.
- [ ] ADR: one contract holding many stokvels (D4 in the doc).
**Files:**
- Create: `contracts/README.md`, `contracts/abi/Stokvel.json` (exported ABI the backend loads), `docs/adr/NNNN-one-contract-many-stokvels.md`
- Change: `contracts/package.json` (ABI export script)
**Done when:** the backend can load the ABI without copying it by hand.

#### R1-06. Cancel and refund in the contract
**Owner:** Kerry · **Milestone:** Extensions Beyond the Brief · **Size:** M · **Type:** extension · **Depends on:** #208 approved · **Refs:** doc P4
- [ ] `cancel`, `refund` and events `StokvelCancelled`, `ContributionRefunded`.
- [ ] Pause also blocks refunds.
- [ ] Tests for cancel with and without finalised rounds.
**Files:**
- Change: `contracts/src/Stokvel.sol` (`cancel`, `refund`, events), `contracts/test/`, `contracts/abi/Stokvel.json`
**Done when:** a refundable contribution can be returned once and only once.

---

### Role 2: Chain integration and stokvel domain (Claire)

_Rebalanced 2026-10-07: R2-12 and R2-13 (contract-facing worker tasks) moved to Kerry, and R2-05 and R2-06 (tables) to Mridula, to cut Claire's load. Claire reviews them and keeps the shared pattern (R2-04, `evm_service.py`). Her PR #211 already covers R2-02a and part of R2-02. R2-03 (remove XRPL imports and update docs) moved from Katlego to Claire, with Sian supporting, because Claire is already removing XRPL._

#### R2-01. EVM settings
**Status:** partly done in PR #211 (open, not merged): `.env.example` documents the `EVM_*` settings (RPC, chain id, explorer, UCTUSD contract and decimals, encryption key, treasury address and key). Still to do: `config.py`, `STOKVEL_CONTRACT_ADDRESS`, `MAX_STOKVEL_MEMBERS`, `.env.minimal.example`, and marking the XRPL variables decommissioned.
**Owner:** Claire · **Milestone:** EVM wallet setup and switch over · **Size:** S · **Type:** core · **Refs:** doc §2, D11
- [ ] Add `EVM_RPC_URL`, `EVM_CHAIN_ID`, `UCTUSD_CONTRACT_ADDRESS`, `STOKVEL_CONTRACT_ADDRESS`, `EVM_TREASURY_ADDRESS`, `EVM_TREASURY_KEY_ENCRYPTED`, `EVM_ENCRYPTION_KEY`, `MAX_STOKVEL_MEMBERS` to `config.py`, `.env.example` and (if needed to run locally) `.env.minimal.example`. The Treasury private key is stored **Fernet-encrypted in `.env`** for now (no database column); `.env.example` holds placeholders only.
- [ ] Mark the XRPL variables decommissioned, unread by any EVM path; do not delete them.
**Files:**
- Change: `api/remitx_api/config.py`, `.env.example`, `.env.minimal.example`, `api/tests/test_config.py`, `tools/loadtest/loadtest.env`
**Done when:** the app starts with only the new variables set.

#### R2-02. `evm_service.py`: connect, load key, send and confirm
**Status:** partly done in PR #211 (open, not merged): the worker-only key loader in `evm_service.py`, `test_evm_service.py` and the `web3` dependency. Still to do: the RPC connection, `send_transaction` with receipt, the burn call, and repointing `tasks.py`. Note: PR #211's log redaction also hides EVM transaction hashes in logs (they look like keys) until exact-value redaction lands in #204.
**Owner:** Claire · **Milestone:** EVM wallet setup and switch over · **Size:** M · **Type:** core · **Depends on:** #205, R2-01 · **Refs:** brief §7.2, §7.4
- [ ] web3.py connection to the RPC; swap `xrpl-py` for `web3` in `api/pyproject.toml`.
- [ ] Read `EVM_TREASURY_KEY_ENCRYPTED` from the environment and decrypt it with `EVM_ENCRYPTION_KEY` in the worker only.
- [ ] `send_transaction` that waits for the receipt and returns hash and block.
- [ ] Unit tests against a stub provider.
**Files:**
- Create: `api/remitx_worker/evm_service.py`, `api/tests/test_evm_service.py`
- Change: `api/pyproject.toml` (`xrpl-py` → `web3`), `api/remitx_worker/tasks.py` (call sites)
**Done when:** the worker can send a test transaction and read its receipt.

#### R2-02a. Generate the Treasury Wallet and encrypt its key into `.env`
**Status:** done in PR #211 (open, not merged): `platform_wallet/scripts/create_evm_platform_wallet.py` creates the address, Fernet-encrypts the key into `.env` with a separate `EVM_ENCRYPTION_KEY`, keeps a 0600 backup outside the repo, and is idempotent. Still to do: record the address in doc §2.
**Owner:** Claire · **Milestone:** EVM wallet setup and switch over · **Size:** S · **Type:** core · **Refs:** brief §7.4; existing `platform_wallet/` script, #205
- [ ] Rewrite `platform_wallet/scripts/create_xprl_platform_wallet.py` to generate an EVM key (no faucet wallet, no trust line).
- [ ] Fernet-encrypt the key and write `EVM_TREASURY_ADDRESS` and `EVM_TREASURY_KEY_ENCRYPTED` into `.env`; print only the address, never the key.
- [ ] Share the encrypted value and `EVM_ENCRYPTION_KEY` with the team through a private channel, not git.
**Files:**
- Create (done in PR #211): `platform_wallet/scripts/create_evm_platform_wallet.py`
- Change: `platform_wallet/scripts/requirements.txt` (done in PR #211), `platform_wallet/pyproject.toml`
- Delete: `platform_wallet/scripts/create_xprl_platform_wallet.py` (the old XRPL script; see R2-03)
- Writes `EVM_TREASURY_ADDRESS` and `EVM_TREASURY_KEY_ENCRYPTED` into the local `.env` (not committed).
**Done when:** `.env` holds the encrypted key and address, and the key never appears in output or logs.

#### R2-02b. Fund the Treasury Wallet (test XRP for gas, UCTUSD for contributions)
**Status:** not done. The wallet script in PR #211 reads native and UCTUSD balances, which covers part of the balance check; UCTUSD funding is still pending.
**Owner:** Claire (supports: Sian for the balance check) · **Milestone:** EVM wallet setup and switch over · **Size:** S · **Type:** core · **Depends on:** R2-02a · **Refs:** brief §7.2, §8; #205 setup list
- [ ] Request test XRP from the XRPL EVM faucet (select Testnet) for the Treasury address; confirm it arrives.
- [ ] Send the Treasury address to Marc (LVNMAR013@myuct.ac.za) to receive UCTUSD from the distributor; confirm the UCTUSD balance.
- [ ] Fund the contract **deployer** address with test XRP the same way (separate address from the Treasury Wallet; see R1-04).
- [ ] Add a small balance-check command (XRP and UCTUSD) to the `platform_wallet/` scripts so anyone can see whether the wallet can still pay gas and contributions.
- [ ] Note the expected demo need in the ticket: gas plus 3 members × 3 rounds of the contribution amount, with a margin.
**Files:**
- Create: `platform_wallet/scripts/check_balances.py` (XRP and UCTUSD balance check)
- Otherwise no code: faucet and UCTUSD requests are manual.
**Done when:** the Treasury Wallet shows both balances above the demo need, and the check command prints them.

#### R2-03. Remove XRPL imports and update docs
**Owner:** Claire (moved from Katlego; supports: Sian) · **Milestone:** EVM wallet setup and switch over · **Size:** S · **Type:** core · **Depends on:** R2-02 · **Refs:** #204
- [ ] No `import xrpl` left under `api/`.
- [ ] Update CLAUDE.md ("XRPL Testnet only"; the key-storage constraint should say the encrypted key sits in `.env`), DEPLOYMENT.md, CONTEXT.md, `Transaction_Flow_Context.md`.
- [ ] Replace hard-coded RLUSD or `uctusd` strings in the frontend with the OpenAPI enums.
**Files:**
- Change: `api/remitx_worker/tasks.py`, `api/remitx_worker/reclaim.py`, `api/remitx_api/services/queue_service.py`, `api/remitx_api/services/settlement_recovery_service.py`, `api/remitx_api/services/remittance_service.py`, `api/remitx_api/controllers/remittance_controller.py`, `CLAUDE.md`, `CONTEXT.md`, `docs/DEPLOYMENT.md`, `docs/Transaction_Flow_Context.md`, `frontend/app/components/landing/trust-note.tsx`, `frontend/app/components/landing/landing-footer.tsx`, `frontend/app/components/auth-split-layout.tsx`, `frontend/app/lib/site.ts`
- Delete: `api/remitx_worker/xrpl_service.py`, `platform_wallet/scripts/create_xprl_platform_wallet.py`
- Run `grep -ri xrpl api/` to find the rest.
**Done when:** `grep -ri xrpl api/` finds only the decommissioned settings.

#### R2-04. Group tables: `stokvels`, `stokvel_members`, `stokvel_invitations`
**Owner:** Claire · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Refs:** doc §3
- [ ] ORM models inheriting `Base`, each imported in `models/orm/__init__.py`.
- [ ] One Alembic migration; `alembic check` clean.
- [ ] Decide row-level security (like the ledger tables) and record it in doc §3.
**Files:**
- Create: `api/remitx_api/models/orm/stokvel.py`, `api/remitx_api/models/orm/stokvel_member.py`, `api/remitx_api/models/orm/stokvel_invitation.py`, `api/remitx_api/repositories/stokvel_repository.py`, `api/remitx_api/repositories/stokvel_member_repository.py`, `api/remitx_api/repositories/stokvel_invitation_repository.py`, `api/alembic/versions/V…__stokvel_group_tables.py`, `api/tests/test_stokvel_group_models.py`
- Change: `api/remitx_api/models/orm/__init__.py`, `api/remitx_api/db/rls.py` and `api/tests/test_rls.py` (if row-level security is added), `docs/stokvel_integration.md` (§3 RLS decision)
**Done when:** the migration applies and rolls back on Postgres and the tests' SQLite schema.

#### R2-05. Cycle tables: `stokvel_cycles`, `stokvel_rounds`, `stokvel_cycle_members`
**Owner:** Mridula (moved from Claire; supports: Claire) · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Depends on:** R2-04 · **Refs:** doc §3
- [ ] Models, migration and `alembic check`, as above.
- [ ] `stokvel_cycle_members` holds payout position, payout beneficiary, payout currency and a `locked` flag.
**Files:**
- Create: `api/remitx_api/models/orm/stokvel_cycle.py`, `api/remitx_api/models/orm/stokvel_round.py`, `api/remitx_api/models/orm/stokvel_cycle_member.py`, `api/remitx_api/repositories/stokvel_cycle_repository.py`, `api/alembic/versions/V…__stokvel_cycle_tables.py`, `api/tests/test_stokvel_cycle_models.py`
- Change: `api/remitx_api/models/orm/__init__.py`
**Done when:** a cycle with three members and three rounds can be inserted.

#### R2-06. Contribution table: `stokvel_contributions`
**Owner:** Mridula (moved from Claire; supports: Claire) · **Milestone:** Stokvel Backend Domain · **Size:** S · **Type:** core · **Depends on:** R2-05 · **Refs:** doc §3, §3 idempotency rules
- [ ] Model and migration with UNIQUE (`cycle_id`, `round`, `member_id`).
- [ ] Columns for fiat amount, token amount, tx id, on-chain hash, block number, status.
**Files:**
- Create: `api/remitx_api/models/orm/stokvel_contribution.py`, `api/remitx_api/repositories/stokvel_contribution_repository.py`, `api/alembic/versions/V…__stokvel_contributions.py`, `api/tests/test_stokvel_contribution_model.py`
- Change: `api/remitx_api/models/orm/__init__.py`
**Done when:** a second contribution for the same member and round is rejected by the database.

#### R2-07. Create and list stokvels (existing #209, narrowed)
See "Edits". Owner Claire. Size M. Tasks: `POST /stokvels` (KYC-approved creator, caller becomes Organiser and first Member), `GET /stokvels` (own stokvels and pending invitations), controller and thin routes, `export_openapi.py`.
**Files:**
- Create: `api/remitx_api/models/schemas/stokvel.py`, `api/remitx_api/controllers/stokvel_controller.py`, `api/remitx_api/routes/stokvels.py`, `api/remitx_api/errors/stokvels.py`, `api/tests/test_stokvels_route.py`
- Change: `api/remitx_api/routes/__init__.py`, `api/remitx_api/errors/__init__.py`, `api/remitx_api/openapi.py` (new `stokvels` Tag, if tags are declared there), `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)

#### R2-08. Invitations: invite, accept, decline
**Owner:** Claire · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Depends on:** R2-07 · **Refs:** CONTEXT.md; doc §5, §12
- [ ] `POST /stokvels/{id}/invitations` by account reference; reject non-KYC-approved invitee (403) and wrong-currency account (422).
- [ ] `POST /invitations/{id}/accept` and `/decline`; only the invitee may call them.
- [ ] Enforce `MAX_STOKVEL_MEMBERS`.
**Files:**
- Create: `api/remitx_api/controllers/stokvel_invitation_controller.py`, `api/remitx_api/routes/stokvel_invitations.py`, `api/tests/test_stokvel_invitations_route.py`
- Change: `api/remitx_api/models/schemas/stokvel.py`, `api/remitx_api/errors/stokvels.py`, `api/remitx_api/repositories/account_repository.py` (look up the invitee by account reference), `api/remitx_api/routes/__init__.py`, `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** the examples in #209 return the stated codes and nobody becomes a member without accepting.

#### R2-09. Payout order and beneficiary
**Owner:** Claire · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Depends on:** R2-05, R2-08 · **Refs:** brief §2 steps 1–2; doc §5
- [ ] `PUT /stokvels/{id}/payout-order` (Organiser only, before a cycle starts).
- [ ] `PUT /stokvels/{id}/members/me/beneficiary`: choose an existing beneficiary and an existing payout-currency account.
- [ ] Reject changes once the cycle is locked.
**Files:**
- Create: `api/tests/test_stokvel_setup_route.py`
- Change: `api/remitx_api/controllers/stokvel_controller.py`, `api/remitx_api/routes/stokvels.py`, `api/remitx_api/models/schemas/stokvel.py`, `api/remitx_api/repositories/stokvel_cycle_repository.py`, `api/remitx_api/repositories/beneficiary_repository.py` (read only: existing beneficiary), `api/remitx_api/repositories/account_repository.py` (read only: payout-currency account), `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** order and beneficiary can be set and re-set until the cycle starts, then not.

#### R2-10. Start a cycle
**Owner:** Claire · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Depends on:** R1-04, R2-09, R2-02 · **Refs:** doc §5, §12 step 5
- [ ] `POST /stokvels/{id}/cycles`: needs at least 2 accepted members, each with a beneficiary.
- [ ] In one transaction: pending invitations become `lapsed`, membership, order and beneficiaries lock, token contribution amount is fixed.
- [ ] Queue `createStokvel` and `startCycle` through the worker, passing round start times, deadlines and payout times.
**Files:**
- Create: `api/remitx_api/controllers/stokvel_cycle_controller.py`, `api/remitx_api/routes/stokvel_cycles.py`, `api/remitx_worker/stokvel_contract.py` (wrapper over the ABI: `createStokvel`, `startCycle`, `contribute`, `finalise`), `api/remitx_worker/stokvel_tasks.py` (create, imported by `celery_app.py`), `api/tests/test_stokvel_start_cycle.py`
- Change: `api/remitx_api/services/queue_service.py` (enqueue by task name), `api/remitx_worker/celery_app.py`, `api/remitx_api/services/exchange_rate_service.py` (read only: token amount at cycle start), `api/remitx_api/routes/__init__.py`, `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** a cycle starts with one invitation still pending and that invitation shows `lapsed`; one member, or a member without a beneficiary, is rejected.

#### R2-11. Contribution API and pending legs
**Owner:** Claire · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Depends on:** R2-06, R3-01, D4 · **Refs:** brief §7.2; doc §3, §5
- [ ] `POST /stokvels/{id}/contributions`: lock the user, check KYC standing, balance and limits, insert pending legs in one transaction (shape of `remittance_service.confirm_remittance`).
- [ ] Extend `RemittanceRepository.sent_zar` (or add a parallel sum) so contributions count toward the member's own limits.
- [ ] Queue `stokvel.submit_contribution` by name.
**Files:**
- Create: `api/remitx_api/controllers/stokvel_contribution_controller.py`, `api/remitx_api/routes/stokvel_contributions.py`, `api/tests/test_stokvel_contribution_route.py`
- Change: `api/remitx_api/services/remittance_service.py` (pattern to copy; shared helpers only), `api/remitx_api/repositories/remittance_repository.py` (`sent_zar` or a parallel sum), `api/remitx_api/services/send_limits.py`, `api/remitx_api/repositories/transaction_repository.py`, `api/remitx_api/repositories/account_repository.py`, `api/remitx_api/services/queue_service.py`, `api/remitx_api/routes/__init__.py`, `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** a contribution is a `pending` record plus ledger legs, and over-limit or short-balance requests are refused.

#### R2-12. Worker tasks: submit and confirm a contribution
**Owner:** Kerry (moved from Claire; supports: Claire) · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Depends on:** R2-02, R2-11, R1-04 · **Refs:** brief §7.2; doc §4
- [ ] `stokvel.submit_contribution`: guarded claim `pending → processing`, calls `contribute`; redelivery is a no-op.
- [ ] `stokvel.confirm_contribution`: DB only, retry-safe; `confirmed` only after the receipt, `failed` on revert.
- [ ] Tests: duplicate message, reverted transaction.
**Files:**
- Create: `api/tests/test_worker_stokvel_contribution.py`
- Change: `api/remitx_worker/stokvel_tasks.py` (`stokvel.submit_contribution`, `stokvel.confirm_contribution`), `api/remitx_worker/stokvel_contract.py`, `api/remitx_worker/evm_service.py`, `api/remitx_api/services/queue_service.py`
**Done when:** a reverted transaction never shows as paid, and a replayed message does not pay twice.

#### R2-13. Event sync
**Owner:** Kerry (moved from Claire; supports: Claire) · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Depends on:** R1-04, R2-12 · **Refs:** doc §4
- [ ] `stokvel.sync_events` beat task reads logs from the last processed block.
- [ ] Apply `ContributionMade`, `RoundFinalised` (queue `stokvel.release_pool` for Sian's ticket), `CycleClosed`.
- [ ] Replaying a block changes nothing.
**Files:**
- Create: `api/remitx_api/models/orm/stokvel_sync_state.py` (last processed block; table listed in doc §3), `api/alembic/versions/V…__stokvel_sync_state.py`, `api/tests/test_stokvel_sync_events.py`
- Change: `api/remitx_worker/stokvel_tasks.py` (`stokvel.sync_events`), `api/remitx_worker/celery_app.py` (beat entry), `api/remitx_api/config.py` (sync interval), `.env.example`, `api/remitx_api/models/orm/__init__.py`
**Done when:** replaying the same events leaves the database unchanged.

#### R2-14. Member screen data: `GET /stokvels/{id}`
**Owner:** Claire · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Depends on:** R2-12 · **Refs:** brief §7.3; doc §5
- [ ] Group, contribution, schedule, order, paid and outstanding, current round, payout and remittance status, transaction hashes, remittance reference.
- [ ] Response model inherits `Schema`; `export_openapi.py`.
**Files:**
- Create: `api/tests/test_stokvel_member_view.py`
- Change: `api/remitx_api/controllers/stokvel_controller.py`, `api/remitx_api/routes/stokvels.py`, `api/remitx_api/models/schemas/stokvel.py`, `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** the member screen can be built from this one response.

#### R2-15. Continue or leave after a cycle
**Owner:** Claire · **Milestone:** Extensions Beyond the Brief · **Size:** M · **Type:** extension · **Depends on:** R2-10 · **Refs:** doc §5, §12 step 8
- [ ] `POST /stokvels/{id}/members/me/continuation`; allow a new beneficiary.
- [ ] Organiser resets the order and starts a new cycle.
**Files:**
- Create: `api/tests/test_stokvel_continuation.py`
- Change: `api/remitx_api/controllers/stokvel_cycle_controller.py`, `api/remitx_api/routes/stokvel_cycles.py`, `api/remitx_api/models/schemas/stokvel.py`, `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** a closed cycle can be followed by a second one.

---

### Role 3: Settlement and payout (Sian)

_Rebalanced 2026-10-07: R3-07, R3-08, R3-10 and R3-12 (admin pause, manual finalise, audit actions and the reconciliation check) moved to Katlego, who owns security and worked on the FSE settlement code with Sian. Sian keeps the ledger and settlement chain: R3-01 to R3-06, R3-09 and R3-11._


#### R3-01. Ledger changes: `STOKVEL` account type and new transaction types
**Owner:** Sian · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Refs:** doc §3 "Ledger changes", D9
- [ ] Add `STOKVEL` to `accounts_type_valid`; relax `accounts_owner_matches_type` and `accounts_reference_matches_type` for it.
- [ ] Add `stokvel_contribution`, `stokvel_pool_release`, `stokvel_refund` to `transactions_type_valid` (precedent: `V20260921_1400__add_burn_and_payout_transaction_types.py`).
- [ ] Migration, `alembic check`, ADR "stokvel ledger account".
**Files:**
- Create: `api/alembic/versions/V…__stokvel_ledger_account_and_types.py`, `api/tests/test_stokvel_ledger.py`, `docs/adr/NNNN-stokvel-ledger-account.md`
- Change: `api/remitx_api/models/orm/account.py` (type and CHECK constraints), `api/remitx_api/models/orm/transaction.py` (transaction types), `api/remitx_api/repositories/account_repository.py`
- Precedent: `V20260921_1400__add_burn_and_payout_transaction_types.py`.
**Done when:** a `STOKVEL` account can be inserted, and the three new types are accepted.

#### R3-02. Quote sender can be a stokvel, and chain-neutral names
**Owner:** Sian · **Milestone:** Stokvel Backend Domain · **Size:** M · **Type:** core · **Refs:** doc §3
- [ ] Make `quotes.sender_user_id` nullable and add `stokvel_id`.
- [ ] Rename `xrpl_tx_hash` to `onchain_tx_hash` (migration, ORM, `transfer_timeline.py`, `remittance_controller.py`, settlement recovery, frontend field).
- [ ] Rename `REMITX_XRPL_WALLET` to `REMITX_EVM_WALLET` and the seeded label; update `remittance_service.py` to match.
**Files:**
- Create: `api/alembic/versions/V…__quote_sender_stokvel_and_onchain_names.py`
- Change: `api/remitx_api/models/orm/quote.py`, `api/remitx_api/models/orm/transaction.py`, `api/remitx_api/models/orm/account.py`, `api/remitx_api/models/orm/platform_account_seed.py`, `api/remitx_api/models/schemas/remittance.py`, `api/remitx_api/models/schemas/account.py`, `api/remitx_api/models/schemas/settlement_recovery.py`, `api/remitx_api/controllers/remittance_controller.py`, `api/remitx_api/controllers/account_controller.py`, `api/remitx_api/controllers/settlement_recovery_controller.py`, `api/remitx_api/services/transfer_timeline.py`, `api/remitx_api/services/remittance_service.py`, `api/remitx_api/services/settlement_recovery_service.py`, `api/remitx_api/repositories/remittance_repository.py`, `api/remitx_api/repositories/transaction_repository.py`, `api/remitx_api/repositories/account_repository.py`, `api/remitx_worker/reclaim.py`, `frontend/app/lib/transfers.ts`, `frontend/app/lib/accounts.ts`, `frontend/app/lib/account-history.ts`, `frontend/app/lib/settlement-recovery.ts`, `frontend/app/components/transfers/transfer-timeline.tsx`, existing tests that mention `xrpl_tx_hash` (`api/tests/test_transfer_timeline.py`, `test_remittances_route.py`, `test_accounts_route.py` and others), `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** existing remittance tests still pass with the renamed fields.

#### R3-03. Payout table: `stokvel_payouts`
**Owner:** Sian · **Milestone:** Settlement and Payout · **Size:** S · **Type:** core · **Depends on:** R2-05 · **Refs:** doc §3
- [ ] Model and migration with UNIQUE (`cycle_id`, `round`).
- [ ] Separate columns for release status and remittance status (brief §7.2).
**Files:**
- Create: `api/remitx_api/models/orm/stokvel_payout.py`, `api/remitx_api/repositories/stokvel_payout_repository.py`, `api/alembic/versions/V…__stokvel_payouts.py`, `api/tests/test_stokvel_payout_model.py`
- Change: `api/remitx_api/models/orm/__init__.py`
**Done when:** a second payout row for the same round is rejected.

#### R3-04. Pool release task
**Owner:** Sian · **Milestone:** Settlement and Payout · **Size:** M · **Type:** core · **Depends on:** R3-01, R3-03, R2-13 · **Refs:** brief §7.1, §7.2; doc §4
- [ ] `stokvel.release_pool`: guarded `pending → processing → released`.
- [ ] Credit the `STOKVEL` ledger account on release (`stokvel_pool_release` legs).
- [ ] Test: a second call does not release or credit again.
**Files:**
- Create: `api/remitx_api/services/stokvel_payout_service.py`, `api/tests/test_worker_stokvel_release_pool.py`
- Change: `api/remitx_worker/stokvel_tasks.py` (`stokvel.release_pool`), `api/remitx_api/repositories/transaction_repository.py`, `api/remitx_api/repositories/account_repository.py`
**Done when:** a finalised round credits the stokvel account exactly once.

#### R3-05. Stokvel-sender quote and remittance
**Owner:** Sian · **Milestone:** Settlement and Payout · **Size:** M · **Type:** core · **Depends on:** R3-02, R3-04 · **Refs:** brief §2 step 5, §7.2; doc D6, D8
- [ ] `stokvel.settle_payout`: build the quote with `quote_service.price_remittance`, sender = the stokvel, beneficiary = the scheduled member's locked beneficiary.
- [ ] Fee and margin deducted from the pool; no second charge to the member.
- [ ] Skip `require_can_send` for a stokvel sender (D8).
**Files:**
- Create: `api/tests/test_worker_stokvel_settle_payout.py`
- Change: `api/remitx_worker/stokvel_tasks.py` (`stokvel.settle_payout`), `api/remitx_api/services/quote_service.py` (`price_remittance` with a stokvel sender), `api/remitx_api/services/remittance_service.py` (skip `require_can_send`), `api/remitx_api/repositories/quote_repository.py`, `api/remitx_api/repositories/remittance_repository.py`
**Done when:** a released round produces one quote and one remittance with the recipient's beneficiary.

#### R3-06. Hand off to the existing settlement chain and finish the payout
**Owner:** Sian · **Milestone:** Settlement and Payout · **Size:** M · **Type:** core · **Depends on:** R3-05, #206 · **Refs:** brief §7.2; doc §4
- [ ] `settle_payout` enqueues `settle_remittance`, which already hands off to `burn_treasury_tokens` and `confirm_treasury_burn`.
- [ ] Store burn hash, beneficiary credit and remittance reference together on the payout row.
- [ ] Release and remittance status change independently.
**Files:**
- Create: `api/tests/test_stokvel_payout_retry.py`
- Change: `api/remitx_worker/stokvel_tasks.py`, `api/remitx_worker/tasks.py` (`settle_remittance` hand-off), `api/remitx_api/repositories/stokvel_payout_repository.py`
**Done when:** a retried payout does not repeat release, burn or credit.

#### R3-07. Admin pause and unpause routes
**Owner:** Katlego (moved from Sian; supports: Sian) · **Milestone:** Settlement and Payout · **Size:** M · **Type:** core · **Depends on:** R1-03, R3-12 · **Refs:** brief §7.1, §7.3, §7.4; doc §5
- [ ] `POST /admin/stokvel-contract/pause` and `/unpause`, admin permission only. Pause takes a required `reason` in the request body.
- [ ] Audit log entry via `record_audit` (`stokvel.contract.paused` / `stokvel.contract.unpaused`, reason required), actions from R3-12.
- [ ] The backend refuses to submit contributions while paused and reports the paused state.
**Files:**
- Create: `api/remitx_api/routes/admin/stokvel_contract.py`, `api/remitx_api/controllers/stokvel_admin_controller.py`, `api/alembic/versions/V…__add_stokvel_contract_permission.py`, `api/tests/test_admin_stokvel_contract.py`
- Change: `api/remitx_api/models/orm/permission.py` (new permission code), `api/remitx_api/models/orm/rbac_seed.py` (grant to the admin role), `api/remitx_worker/stokvel_contract.py` (`pause`, `unpause`, `paused`), `api/remitx_api/errors/stokvels.py`, `api/remitx_api/routes/__init__.py`, `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** pausing from the API stops a contribution, and the audit log shows who did it.

#### R3-08. Pool reconciliation check
**Owner:** Katlego (moved from Sian; supports: Sian) · **Milestone:** Settlement and Payout · **Size:** M · **Type:** core · **Depends on:** R3-06 · **Refs:** #207 (Option A)
- [ ] UNIQUE (round, entry type) so a second burn for a round cannot be inserted.
- [ ] Test: the burn equals exactly the round's pool, never more (the wallet also holds float).
- [ ] A check that on-chain balance equals unburned float computed from the ledger; usable in the demo.
**Files:**
- Create: `api/remitx_api/services/stokvel_reconciliation_service.py`, `api/scripts/check_pool_reconciliation.py` (demo check command), `api/alembic/versions/V…__unique_burn_per_round.py`, `api/tests/test_stokvel_reconciliation.py`
- Change: `api/remitx_api/repositories/transaction_repository.py`, `api/remitx_worker/evm_service.py` (balance read)
**Done when:** the check passes after three rounds in the seeded demo.

#### R3-09. Refund task and cancel route
**Owner:** Sian · **Milestone:** Extensions Beyond the Brief · **Size:** M · **Type:** extension · **Depends on:** #208, R1-06, R3-12 · **Refs:** doc P4
- [ ] `stokvel.refund`, guarded so a retry never refunds twice.
- [ ] `POST /admin/stokvels/{id}/cancel`, with a required `reason` in the request body.
- [ ] Refund the original fiat amount to the account it came from.
- [ ] Audit log entry for the cancel (`stokvel.cancelled`, reason required), action from R3-12.
**Files:**
- Create: `api/tests/test_worker_stokvel_refund.py`
- Change: `api/remitx_worker/stokvel_tasks.py` (`stokvel.refund`), `api/remitx_api/controllers/stokvel_admin_controller.py`, `api/remitx_api/routes/admin/stokvels.py`, `api/remitx_api/models/orm/stokvel_contribution.py` (refund statuses, plus a migration), `api/remitx_api/repositories/transaction_repository.py`, `api/remitx_worker/stokvel_contract.py` (`cancel`, `refund`), `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** cancelling after one finalised round refunds only the unfinalised contributions.

#### R3-10. Admin manual finalise route
**Owner:** Katlego (moved from Sian; supports: Sian) · **Milestone:** Settlement and Payout · **Size:** S · **Type:** core (pending P5 approval) · **Depends on:** R3-04, R3-07, R3-12 · **Refs:** brief §7.1, §7.3; doc P5, §5
- [ ] `POST /admin/stokvels/{id}/rounds/{n}/finalise`, admin permission only; the operator calls `finalise` on the contract.
- [ ] A round that is not ready returns 409 `round_not_finalisable` (contract `NotYetFinalisable`).
- [ ] Audit log entry via `record_audit` (`stokvel.round.finalised_manually`), action from R3-12.
- [ ] Test: automatic and manual finalise on the same round release and credit only once.
**Files:**
- Create: `api/remitx_api/routes/admin/stokvels.py`, `api/tests/test_admin_stokvel_finalise.py`
- Change: `api/remitx_api/controllers/stokvel_admin_controller.py`, `api/remitx_api/models/orm/permission.py` and `api/remitx_api/models/orm/rbac_seed.py` (permission, plus a migration), `api/remitx_api/errors/stokvels.py` (`round_not_finalisable`), `api/remitx_worker/stokvel_contract.py` (`finalise`), `api/remitx_api/routes/__init__.py`, `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
**Done when:** a ready round can be finalised by the admin, a blocked one is rejected, and a double trigger does not release twice.

#### R3-11. Scheduled release of due rounds
**Owner:** Sian · **Milestone:** Settlement and Payout · **Size:** M · **Type:** core · **Depends on:** R3-04, R2-13 · **Refs:** brief §7.1; doc D12, §4
- [ ] Beat task `stokvel.release_due_rounds`: find rounds whose payout time has passed and whose paid condition holds but are not released; queue `stokvel.release_pool` for each.
- [ ] Idempotent with the contribution-triggered release and the admin finalise (R3-10): one release, one credit.
- [ ] Tests: everyone pays early and the round releases only after the payout time; a member pays after the payout time and the round releases; a double trigger releases once.
**Files:**
- Create: `api/tests/test_worker_stokvel_release_due_rounds.py`
- Change: `api/remitx_worker/stokvel_tasks.py` (`stokvel.release_due_rounds`), `api/remitx_worker/celery_app.py` (beat entry), `api/remitx_api/config.py` (interval), `.env.example`, `api/remitx_api/repositories/stokvel_cycle_repository.py` (due-round query)
**Done when:** a fully paid round releases on its payout time without anyone clicking anything.

#### R3-12. Stokvel audit actions for admin actions
**Owner:** Katlego (moved from Sian; supports: Sian) · **Milestone:** Settlement and Payout · **Size:** S · **Type:** core · **Refs:** doc §5 "Audit log of admin actions"; existing `audit_service.record_audit`, `GET /admin/audit`
- [ ] Add audit actions `stokvel.contract.paused`, `stokvel.contract.unpaused`, `stokvel.round.finalised_manually`, `stokvel.cancelled` and subjects `stokvel`, `stokvel_contract` (with a fixed constant subject id for the contract) to the enums.
- [ ] Entries hold ids, round numbers, statuses and transaction hashes only; no PII. `reason` required for pause and cancel.
- [ ] Optional `action_prefix` filter on `GET /admin/audit` so one call lists every `stokvel.` entry.
- [ ] Tests: each action writes one entry in the same transaction as the admin action; a rolled-back action leaves no entry; the new filter works.
- [ ] Update doc §5 if the action names change.
**Files:**
- Change: `api/remitx_api/models/orm/audit_log.py` (new enum members), `api/remitx_api/controllers/audit_controller.py` and `api/remitx_api/routes/admin/audit.py` (optional filter), `api/remitx_api/models/schemas/audit.py` (if it lists subjects), `api/tests/test_audit_log.py`, `frontend/openapi.json` (regenerated by `python scripts/export_openapi.py`)
- Create: `api/tests/test_stokvel_audit.py`
**Done when:** the pause, resume, manual finalise and cancel actions each leave an audit entry that shows up in `GET /admin/audit`, and nothing else writes to it.

---

### Role 4: Frontend (Karabo; Mridula supports)


#### R4-01. Screens from the product team's user journey
**Owner:** Karabo (supports: Mridula) · **Milestone:** Finished Frontend Screens · **Size:** M · **Type:** core · **Refs:** brief §7.3
- [ ] Meet the product team and collect their journey.
- [ ] List the screens and who sees each (member, organiser, admin).
- [ ] Add the list to doc §5 or a comment on this ticket.
**Files:**
- None in code. Result goes in `docs/stokvel_integration.md` (§5) or a comment on this ticket.
**Done when:** the screen list is agreed with product and matches the brief's §7.3.
**Note:** product confirmations are also needed on fees (pool or members, and whether the fee and margin are converted to fiat at finalisation), contribution amount, the informational deadline and member limits; see the product deviations file.

#### R4-02. Mocked OpenAPI data and route scaffolding
**Owner:** Karabo · **Milestone:** Finished Frontend Screens · **Size:** M · **Type:** core · **Depends on:** R4-01 · **Refs:** CLAUDE.md frontend rules
- [ ] Add routes in `app/routes.ts` for the screens; run `npm run typecheck`.
- [ ] Mock responses for the shapes in doc §5, so work does not wait for the API.
**Files:**
- Create: `frontend/app/routes/app/stokvels.tsx`, `frontend/app/routes/app/stokvel.tsx`, `frontend/app/routes/admin/stokvel-contract.tsx`, `frontend/app/lib/stokvels.ts`, `frontend/app/lib/stokvels.mock.ts`
- Change: `frontend/app/routes.ts`, `frontend/app/routes/app/app.routes.ts`, `frontend/app/routes/admin/admin.routes.ts`, `frontend/app/routes/app/app.routes.test.ts`, `frontend/app/routes/admin/admin.routes.test.ts`, `frontend/app/components/app-dashboard/app-nav.tsx`, `frontend/app/components/admin/admin-nav.tsx`
**Done when:** empty screens render on mocked data.

#### R4-03. Stokvel list and create form
**Owner:** Karabo · **Milestone:** Finished Frontend Screens · **Size:** M · **Type:** core · **Depends on:** R4-02 · **Refs:** #209
- [ ] List of own stokvels and pending invitations.
- [ ] Create-stokvel form (name, Stokvel currency, contribution, schedule with a deadline and a payout time per round).
**Files:**
- Create: `frontend/app/routes/app/stokvel-new.tsx`, `frontend/app/components/stokvels/stokvel-list.tsx`, `frontend/app/components/stokvels/create-stokvel-form.tsx`
- Change: `frontend/app/routes/app/stokvels.tsx`, `frontend/app/lib/stokvels.ts` (and a `stokvels.test.ts`)
**Done when:** both screens work on mocked data.

#### R4-04. Invitations: invite, accept, decline
**Owner:** Karabo (supports: Mridula) · **Milestone:** Finished Frontend Screens · **Size:** S · **Type:** core · **Depends on:** R4-03 · **Refs:** #209; doc §12
- [ ] Organiser invites by account reference; invitee sees Accept and Decline.
- [ ] Show that pending invitations lapse when the Organiser starts the cycle.
**Files:**
- Create: `frontend/app/components/stokvels/invite-member-form.tsx`, `frontend/app/components/stokvels/invitation-card.tsx`
- Change: `frontend/app/routes/app/stokvels.tsx`, `frontend/app/routes/app/stokvel.tsx`
**Done when:** the invite and accept flow works on mocks.

#### R4-05. Stokvel detail and contribute
**Owner:** Karabo · **Milestone:** Finished Frontend Screens · **Size:** M · **Type:** core · **Depends on:** R4-02 · **Refs:** brief §7.3
- [ ] Group, amount, schedule, payout order, paid and outstanding, current round.
- [ ] Payout status, transaction hashes, remittance reference.
- [ ] Contribute button with the error messages from doc §6.
**Files:**
- Create: `frontend/app/components/stokvels/contribution-panel.tsx`, `frontend/app/components/stokvels/round-schedule.tsx`, `frontend/app/components/stokvels/payout-status.tsx`, `frontend/app/lib/stokvel-errors.ts` (doc §6 messages)
- Change: `frontend/app/routes/app/stokvel.tsx`, `frontend/app/components/evm/tx-hash.tsx`
**Done when:** a member can see everything §7.3 lists for the member screen.

#### R4-06. Beneficiary picker and organiser setup screens
**Owner:** Karabo (supports: Mridula) · **Milestone:** Finished Frontend Screens · **Size:** M · **Type:** core · **Depends on:** R4-02 · **Refs:** brief §7.3 ("reuse FSE's existing beneficiary screen")
- [ ] Member picks an existing beneficiary and payout currency; the existing add-beneficiary form is reused, not rebuilt.
- [ ] Organiser sets payout order and starts the cycle.
**Files:**
- Create: `frontend/app/components/stokvels/beneficiary-picker.tsx`, `frontend/app/components/stokvels/payout-order-editor.tsx`, `frontend/app/components/stokvels/start-cycle-panel.tsx`, `frontend/app/routes/app/stokvel-setup.tsx`
- Change: `frontend/app/routes.ts`, `frontend/app/routes/app/app.routes.ts`, `frontend/app/components/beneficiaries/beneficiary-list.tsx` and `frontend/app/components/beneficiaries/add-beneficiary-form.tsx` (reused, not rebuilt)
**Done when:** these steps work on mocks and use shadcn components only.

#### R4-07. Admin pause and resume control
**Owner:** Karabo · **Milestone:** Finished Frontend Screens · **Size:** S · **Type:** core · **Refs:** brief §7.3
- [ ] Pause and resume control on the admin screen; shows current state.
**Files:**
- Create: `frontend/app/components/admin/stokvel-pause-card.tsx`
- Change: `frontend/app/routes/admin/stokvel-contract.tsx`, `frontend/app/routes/admin/admin.routes.ts`, `frontend/app/components/admin/admin-nav.tsx`, `frontend/app/lib/permissions.ts` (new permission)
**Done when:** it works on mocks, then wires to R3-07.

#### R4-08. EVM explorer link and error messages
**Owner:** Karabo · **Milestone:** Finished Frontend Screens · **Size:** S · **Type:** core · **Refs:** doc §6
- [ ] EVM explorer variant of the tx-hash component.
- [ ] Map the doc §6 error codes to the messages shown to users.
**Files:**
- Create: `frontend/app/components/evm/tx-hash.tsx` (replaces `components/xrpl/tx-hash.tsx`)
- Change: `frontend/app/components/transfers/xrpl-hash.tsx` (rename to `chain-hash.tsx`), `frontend/app/components/transfers/transfer-timeline.tsx`, `frontend/app/lib/transfers.ts`, `frontend/app/lib/stokvel-errors.ts`
- Delete: `frontend/app/components/xrpl/tx-hash.tsx`
**Done when:** a hash links to the explorer and each error code shows its message.

#### R4-09. Wire screens to the real API
**Owner:** Karabo · **Milestone:** Connect Frontend to Backend · **Size:** L · **Type:** core · **Depends on:** R2-14, R3-07 · **Refs:** CLAUDE.md
- [ ] Run `npm run generate:api` and replace mocks with `useQuery(api.stokvels…)`.
- [ ] Remove mock data.
**Files:**
- Change: `frontend/app/routes/app/stokvels.tsx`, `frontend/app/routes/app/stokvel.tsx`, `frontend/app/routes/app/stokvel-new.tsx`, `frontend/app/routes/app/stokvel-setup.tsx`, `frontend/app/routes/admin/stokvel-contract.tsx`, `frontend/app/components/stokvels/*`, `frontend/app/lib/stokvels.ts`, `frontend/openapi.json` (pulled from the API)
- Delete: `frontend/app/lib/stokvels.mock.ts`
- `app/client/` is generated and gitignored: run `npm run generate:api`.
**Done when:** the member and admin screens work against the deployed QA API.

#### R4-10. Continue or leave screen
**Owner:** Karabo · **Milestone:** Extensions Beyond the Brief · **Size:** S · **Type:** extension · **Depends on:** R2-15
- [ ] End-of-cycle choice and new beneficiary.
**Files:**
- Create: `frontend/app/components/stokvels/continue-or-leave.tsx`
- Change: `frontend/app/routes/app/stokvel.tsx`
**Done when:** it works against R2-15.

#### R4-11. Admin finalise button
**Owner:** Karabo · **Milestone:** Finished Frontend Screens · **Size:** S · **Type:** core (pending P5 approval) · **Depends on:** R4-07 · **Refs:** brief §7.3; doc P5, §6
- [ ] Finalise button per round on the admin screen; shows the doc §6 message when the round is not ready.
**Files:**
- Create: `frontend/app/components/admin/stokvel-finalise-button.tsx`
- Change: `frontend/app/routes/admin/stokvel-contract.tsx` (or a new `routes/admin/stokvels.tsx`), `frontend/app/lib/stokvel-errors.ts`
**Done when:** it works on mocks, then wires to R3-10.

#### R4-12. Stokvel filter on the admin audit page
**Owner:** Karabo · **Milestone:** Finished Frontend Screens · **Size:** S · **Type:** core · **Depends on:** R3-12 · **Refs:** brief §7.3; doc §5
- [ ] Add a stokvel filter (stokvel and stokvel contract subjects) to the existing admin audit page.
- [ ] Show action, actor, stokvel, reason and time; link a transaction hash to the explorer.
**Files:**
- Change: `frontend/app/routes/admin/audit.tsx`, `frontend/app/lib/` (audit helpers, if any)
**Done when:** pausing the contract or manually finalising a round shows up in the stokvel view.

---

### Role 5: Fiat, deploy, security (Katlego)

#### R5-01. Contracts CI job
**Owner:** Katlego · **Milestone:** Testing, Security and Demo · **Size:** S · **Type:** core · **Refs:** brief §7.5
- [ ] A CI job that installs and runs the contract tests on every PR.
**Files:**
- Change: `.github/workflows/ci.yml` (new contracts job), `contracts/package.json` (test script)
**Done when:** a failing contract test fails the PR.

#### R5-02. Render and Terraform EVM variables
**Owner:** Katlego · **Milestone:** EVM wallet setup and switch over · **Size:** M · **Type:** core · **Depends on:** R2-01 · **Refs:** doc §2; DEPLOYMENT.md
- [ ] Add the `EVM_*` and contract settings to the Render services (key and encryption key as secrets).
- [ ] Update DEPLOYMENT.md.
**Files:**
- Change: `infra/envs/qa/main.tf`, `infra/envs/qa/variables.tf`, `infra/envs/prod/main.tf`, `infra/envs/prod/variables.tf`, `.github/scripts/render-sync-env.sh`, `docs/DEPLOYMENT.md`, `.env.example`
**Done when:** the QA stack boots with EVM settings and no XRPL ones.

#### R5-03. Security hardening and checklist
**Status:** the gitleaks rule and the leak tests were done by Claire in PR #211 (open, not merged): the `ethereum-private-key` rule now matches `EVM_*_KEY` names and keys without `0x`, plus `test_evm_key_secrecy.py`, `test_log_redaction.py` and `log_redaction.py`. Remaining here: the §7.4 checklist and the interim storage note. Katlego should not redo the rule or the tests.
**Owner:** Katlego · **Milestone:** Testing, Security and Demo · **Size:** M · **Type:** core · **Depends on:** #205 · **Refs:** brief §7.4
- [x] gitleaks rule for 32-byte hex EVM private keys, next to the XRPL-seed rule (PR #211).
- [x] Tests: no API response or log line contains the key; the API process cannot import the decryption path (PR #211).
- [ ] Short checklist for brief §7.4 incl. "one key controls everything" (from #207).
- [ ] Record the interim storage choice: the encrypted Treasury key and the Fernet key both sit in `.env` for now. `.env` is gitignored and blocked by the pre-commit hook; on Render set them as two separate secrets. Note moving the Fernet key to a secret store as the next step.
**Files:**
- Create: `docs/stokvel_security_checklist.md`
- Already done in PR #211: `.gitleaks.toml` (EVM private key rule), `api/tests/test_evm_key_secrecy.py`, `api/tests/test_log_redaction.py`, `api/remitx_api/log_redaction.py`
- Change: `docs/DEPLOYMENT.md` (secret handling note)
**Done when:** committing an EVM key is blocked, and the leak tests pass.

---

### Role 6: Testing and demo (Mridula)

#### R1-07. Check the UCTUSD burn method
**Owner:** Mridula · **Milestone:** EVM wallet setup and switch over · **Size:** S · **Type:** core · **Refs:** #206
- [ ] Look up the token on the UCTUSD explorer: does it expose `burn(uint256)` or `burnFrom`?
- [ ] If not, confirm the dead-address transfer and that the hash is recorded as the burn.
- [ ] Comment the answer on #206 and doc §8.
**Files:**
- No code. Answer goes on #206 and in `docs/stokvel_integration.md` (§8).
**Done when:** #206 has a definite method.

#### R6-01. Test plan
**Owner:** Mridula · **Milestone:** Testing, Security and Demo · **Size:** S · **Type:** core · **Refs:** brief §7.5
- [ ] Map each required test (contract, settlement retry, demo cases) to a ticket and an owner.
**Files:**
- Create: `docs/stokvel_test_plan.md`
**Done when:** every brief §7.5 item has an owner and a ticket.

#### R6-02. Seeder and load test for EVM
**Owner:** Mridula · **Milestone:** Testing, Security and Demo · **Size:** M · **Type:** core · **Depends on:** R2-02, R3-02 · **Refs:** `tools/seeder`, `tools/loadtest`
- [ ] Update `tools/seeder/remitx_seeder/stories/` for EVM.
- [ ] Update `tools/loadtest/fake_xrpl_worker.py` to simulate the EVM burn.
**Files:**
- Change: `tools/seeder/remitx_seeder/settlement.py`, `tools/seeder/remitx_seeder/scenario.py`, `tools/seeder/remitx_seeder/settings.py`, `tools/seeder/remitx_seeder/verify.py`, `tools/seeder/remitx_seeder/live_tail.py`, `tools/seeder/remitx_seeder/ui/app.py`, `tools/seeder/README.md`, `tools/seeder/.env.qa.example`, `tools/seeder/tests/test_seed_run.py`, `tools/seeder/tests/test_reset.py`, `tools/seeder/tests/conftest.py`, `tools/loadtest/fake_xrpl_worker.py` (rename to `fake_evm_worker.py`), `tools/loadtest/qa_xrpl_timings.sql`, `tools/loadtest/loadtest.env`, `tools/loadtest/docker-compose.yml`, `tools/loadtest/to_canvas.py`, `tools/loadtest/README.md`, `tools/loadtest/tests/test_fake_xrpl_worker.py`, `tools/loadtest/tests/test_profile.py`
**Done when:** the seeder CI job and `make loadtest` pass.

#### R6-03. Demo data: three KYC-approved members and three beneficiaries
**Owner:** Mridula · **Milestone:** Testing, Security and Demo · **Size:** M · **Type:** core · **Depends on:** R6-02, R2-10 · **Refs:** brief §2, §6
- [ ] Seeder story creating a stokvel with three members, KYC-approved, funded, each with a beneficiary.
- [ ] A second state with one invitation still pending (tests the lapse rule).
**Files:**
- Create: `tools/seeder/remitx_seeder/stories/stokvel.py`
- Change: `tools/seeder/remitx_seeder/stories/__init__.py`, `tools/seeder/remitx_seeder/scenario.py`, `tools/seeder/remitx_seeder/ui/app.py`, `tools/seeder/tests/` (a test for the new story)
**Done when:** one command prepares the demo.

#### R6-04. End-to-end: three members, three rounds
**Owner:** Mridula · **Milestone:** Testing, Security and Demo · **Size:** M · **Type:** core · **Depends on:** R3-06, R6-03 · **Refs:** brief §2
- [ ] Automated run of all three rounds, each payout reaching the right beneficiary.
**Files:**
- Create: `api/tests/test_stokvel_three_rounds.py` (local, chain stubbed), `tools/stokvel_demo/run_three_rounds.py` (against the deployed version)
**Done when:** it passes on the deployed version.

#### R6-05. End-to-end: blocked round, duplicate and early finalisation
**Owner:** Mridula (supports: Kerry) · **Milestone:** Testing, Security and Demo · **Size:** M · **Type:** core · **Depends on:** R6-04 · **Refs:** brief §2
- [ ] One member does not pay: the round does not release.
- [ ] A duplicate contribution is rejected.
- [ ] An early `finalise` call is rejected.
**Files:**
- Create: `api/tests/test_stokvel_blocked_duplicate_early.py`, `tools/stokvel_demo/run_blocked_duplicate_early.py` (live demo script)
- Change: `contracts/test/` (early `finalise` rejection)
**Done when:** all three cases are scripted for the live demo.

#### R6-06. Settlement retry test
**Owner:** Mridula (supports: Sian) · **Milestone:** Testing, Security and Demo · **Size:** M · **Type:** core · **Depends on:** R3-06 · **Refs:** brief §7.2, §7.5
- [ ] Retry a failed settlement and assert no second release, burn or credit.
**Files:**
- Create: `api/tests/test_stokvel_settlement_retry.py`
- Model it on `api/tests/test_worker_settle_remittance.py` and `test_worker_burn_treasury_tokens.py`.
**Done when:** the test passes in CI.

#### R6-07. Demo script, rehearsal and backup video
**Owner:** Mridula · **Milestone:** Testing, Security and Demo · **Size:** L · **Type:** core · **Depends on:** R6-05, R6-06 · **Refs:** brief §6
- [ ] Script with timings (rounds a few minutes apart).
- [ ] Before each rehearsal and the live demo, run the wallet balance check from R2-02b; top up test XRP or UCTUSD if low.
- [ ] Monday 26 Oct full rehearsal on the deployed version.
- [ ] Record the backup video.
**Files:**
- Create: `docs/stokvel_demo_script.md`
- The backup video is not stored in the repo.
**Done when:** the backup video exists and the live demo has been rehearsed twice.

---

## Open issues needing tickets

Found in the 2026-10-07 review of this plan and the integration doc. Each needs a ticket (or a decision) before the work it affects starts. IDs are placeholders; owners, sizes and milestones are to be assigned by the team.

#### OI-1. Who calls `finalise`, and which flow is the real one
**Problem:** three descriptions don't line up. §1 says the `contribute` call that completes round N+1 finalises round N in the same transaction. §4 says the `RoundFinalised` event drives the database update. R3-04 and R3-11 say a `stokvel.release_pool` task credits the ledger and the scheduled task queues it, but neither says `release_pool` itself calls the contract's `finalise`. Only the admin route (R3-10) does.
**Needed:** one agreed flow, written into doc §1 and §4: who calls `finalise` (the contribute call, the scheduled task, or `release_pool`), what the event sync does, and who credits the `STOKVEL` ledger account on an automatic release.
**Affects:** R1-01, R2-13, R3-04, R3-10, R3-11, doc D12.
**Owner / size:** to assign (decision, S). Needs the contract owner and the settlement owner.
**Done when:** doc §1 and §4 describe one flow, and the R3-04 and R3-11 checklists say who calls `finalise`.

#### OI-2. ERC-20 approval from the Treasury Wallet to the contract
**Problem:** §1 says `contribute` "pulls" UCTUSD from the Treasury Wallet. That needs the Treasury to approve the contract to spend UCTUSD first. No ticket covers it.
**Needed:** decide who sends the approval and when (once at deployment for a large allowance, or before each contribution), add an allowance check and top-up, and test that `contribute` fails cleanly without it.
**Related:** R1-04 (deploy), R2-02 and R2-02b (wallet and balance check; could also show the allowance), R2-12 (contribution submit).
**Owner / size:** to assign (S).
**Done when:** a `contribute` call from the Treasury Wallet succeeds with the allowance in place, and the approval step is written down.

#### OI-3. Missing dependency on the `stokvel_contract.py` wrapper
**Problem:** R3-07, R3-10 and R3-09 all call `stokvel_contract.py` (`pause`, `unpause`, `finalise`, `cancel`, `refund`). R2-10 creates it, and none of those tickets lists R2-10 as a dependency.
**Needed:** either add R2-10 as a dependency to R3-07, R3-09 and R3-10, or split the wrapper into its own small ticket that the others depend on.
**Owner / size:** to assign (S, or a plan edit only).
**Done when:** every ticket that uses the wrapper lists what creates it.

#### OI-4. Who checks the pause state before accepting a contribution
**Problem:** R3-07 says the backend refuses contributions while the contract is paused and reports the paused state. That logic lives in the contribution API (R2-11) and the submit task (R2-12), and neither depends on R3-07 or mentions the check.
**Needed:** assign the check to a ticket: read `paused()` from the contract, return 503 `stokvel_paused` (doc §6), and decide whether the submit task also re-checks.
**Related:** R1-03, R2-11, R2-12, R3-07, doc §6.
**Owner / size:** to assign (S).
**Done when:** with the contract paused, `POST /stokvels/{id}/contributions` is refused with `stokvel_paused`, and the owning ticket says so.

#### OI-5. Contribution amount: the doc contradicts itself
**Problem:** §1 and §3 already assume a fixed token amount locked at cycle start (`token_contribution_amount`, converted once by the backend). §8 and the product file still ask whether the amount is a fixed token amount or a fixed fiat amount, and how live rates are handled.
**Needed:** a product decision, then make §1, §3 and §8 agree. If the amount is a fixed fiat amount per contribution, the contract's fixed `contribution` and `WrongAmount` check, or who carries the rate movement, have to change.
**Related:** D4 (decides the amount rule), R1-01, R2-11, product file.
**Owner / size:** product decision; D4 owner updates the docs (S).
**Done when:** one amount model is written in §1, §3 and §8, and D4 records it.

## If Role 2 is late

Claire is the backend lead and has the longest chain. If one round is not working end to end by Tue 13 Oct, in this order:
1. Drop R2-15 and R3-09 (already extensions).
2. Move R2-14 to Sian.
3. Move R4-09's wiring to the person who finishes first.

## Order and dependencies

1. **Now:** D1, D3, R4-01, R1-07, R2-01, R2-02a, R2-02b (the funded address unblocks the deploy).
2. **By Fri 9 Oct:** contract deployed (R1-02, R1-04), `evm_service` (R2-02), tables R2-04 to R2-06, ledger R3-01, R3-02.
3. **By Fri 16 Oct:** one round end to end: R2-07 to R2-14, R3-03 to R3-06, R3-12; screens on mocks (R4-02 to R4-08).
4. **By Fri 23 Oct:** R4-09, R4-12, R3-07, R3-10, R3-11, R3-08, R6-04 to R6-06, code freeze.
5. **Mon 26 – Wed 28 Oct:** R6-07 and rehearsal.

## GitHub issues

Created on 2026-10-07 in Katlego-Sekoele/RemitX: 67 new issues and 4 new milestones, with due dates on 8 milestones. Issues for Karabo and Mridula carry the label `for-karabo` or `for-mridula` because they are not repo collaborators yet; assign them when they are added. The OI-1 to OI-5 open issues have no tickets yet, by decision.

**Old issues.** #199, #200, #201, #202, #203, #204, #205, #206 and #209 were closed as not planned (not deleted) and replaced by new issues that carry the original text in a collapsible section; their milestones were cleared so they do not count as progress. Reopen one to revert. #207 and #208 (the decision issues) were kept open and updated in place. PR #211 now says "Part of #277".

| Old issue | Replaced by |
|---|---|
| #199 | #217 (R1-03) |
| #200 | #216 (R1-02) |
| #201 | #273 |
| #202 | #274 |
| #203 | #275 |
| #204 | #276 |
| #205 | #277 |
| #206 | #278 |
| #209 | #229 (R2-07) |

| Ticket | Issue |
|---|---|
| D1 | #212 |
| D3 | #213 |
| D4 | #214 |
| R1-01 | #215 |
| R1-02 | #216 |
| R1-03 | #217 |
| R1-04 | #218 |
| R1-05 | #219 |
| R1-06 | #220 |
| R2-01 | #221 |
| R2-02 | #222 |
| R2-02a | #223 |
| R2-02b | #224 |
| R2-03 | #225 |
| R2-04 | #226 |
| R2-05 | #227 |
| R2-06 | #228 |
| R2-07 | #229 |
| R2-08 | #230 |
| R2-09 | #231 |
| R2-10 | #232 |
| R2-11 | #233 |
| R2-12 | #234 |
| R2-13 | #235 |
| R2-14 | #236 |
| R2-15 | #237 |
| R3-01 | #238 |
| R3-02 | #239 |
| R3-03 | #240 |
| R3-04 | #241 |
| R3-05 | #242 |
| R3-06 | #243 |
| R3-07 | #244 |
| R3-08 | #245 |
| R3-09 | #246 |
| R3-10 | #247 |
| R3-11 | #248 |
| R3-12 | #249 |
| R4-01 | #250 |
| R4-02 | #251 |
| R4-03 | #252 |
| R4-04 | #253 |
| R4-05 | #254 |
| R4-06 | #255 |
| R4-07 | #256 |
| R4-08 | #257 |
| R4-09 | #258 |
| R4-10 | #259 |
| R4-11 | #260 |
| R4-12 | #261 |
| R5-01 | #262 |
| R5-02 | #263 |
| R5-03 | #264 |
| R1-07 | #265 |
| R6-01 | #266 |
| R6-02 | #267 |
| R6-03 | #268 |
| R6-04 | #269 |
| R6-05 | #270 |
| R6-06 | #271 |
| R6-07 | #272 |
