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
| 2026-10-07 | Proposals, Deviations, 1, 5, 6 | Added P5: manual admin finalise as a fallback to automatic finalisation (route `POST /admin/stokvels/{id}/rounds/{n}/finalise`) | |
| 2026-10-07 | 3, 8, 9 | Synced with the product deviations file: recommend keeping the ledger status names; contribution amount, fees (with the fee-to-fiat suggestion), deadline, limits and key storage listed as product confirmations; Treasury Wallet created | |
| 2026-10-07 | Decisions, 8 | D1 records lecturer approval of the EVM move (Marc). Added open question: are the fee and margin converted back to fiat | |
| 2026-10-07 | 9 | GitHub issues recreated from the ticket plan: #199–#206 and #209 closed and replaced (#217, #216, #273–#278, #229); #207 and #208 kept; mapping in the ticket plan ("GitHub issues") | |
| 2026-10-07 | 7, 9, Deviations | TrustMeBank deposits and withdrawals (#202, #203) are now required, not optional | |
| 2026-10-07 | 3, 4, 5, 8, 9 | Review fixes: P2 now mentions the payout time; P5 listed before P6; `stokvel_sync_state` added to section 3; pause and cancel take a `reason`; section 9 records PR #211 (#205 and part of #204); added an open question on log redaction hiding transaction hashes | |
| 2026-10-07 | 5, 8, 9 | Added the stokvel audit log of admin actions (section 5): new audit actions and subjects on the existing `audit_log`, viewed through `GET /admin/audit` | |
| 2026-10-07 | Decisions, Proposals, 1, 3, 4, 8, 11, 12 | D5 amended and D12 added: a round is released only when it is fully paid **and** its payout time has passed (Organiser-set); a scheduled backend task releases due rounds. Deadline stays informational. Added P6 (merge deadline and payout time) | |
| 2026-10-08 | 1, 2, 6, 9, 13, 14 | Section 1 confirmed against the contract as built (DEC-1 #212, R1-01 #215): constructor and deployment arguments, final signatures, `cycle` added to `ContributionMade` and `RoundFinalised`, error `CycleClosed` renamed `CycleNotOpen` (name clash with the event), input-validation errors, view signatures, member IDs are per-stokvel row UUIDs. Cancel and refund marked planned (#220). Section 2: deployer and Treasury Wallet addresses. Section 6: error rename. Sections 9, 13, 14: contract progress, files and functions | |
| 2026-10-08 | 1, 6 | Treasury allowance agreed with the backend: one-off `approve(vault, max)` per contract address, checked before each `contribute` and re-approved if low. Section 6 maps the token's `ERC20InsufficientAllowance` to a backend 500. Backend confirmed sections 1 and 6, and the fixed contribution amount in `createStokvel` | |
| 2026-10-09 | 1 | MVP decision: the contribution amount is fixed per stokvel for all cycles; a new amount means a new stokvel | |
| 2026-10-09 | 2, 8, 9, 10, 13, 14 | Contract work brought up to date: section 2 lists the deploy script's settings and `DEPLOYER_PRIVATE_KEY` (local only); section 8 resolves the contract side of the contribution amount and the Treasury allowance, defers per-cycle amounts, and adds the admin-key question for pause (#244); section 9 marks the contract, tests and pause done (PR #282 merged), deployment in progress (#284) and README/ABI/ADR in review (#285); sections 10, 13 and 14 list the contract features, files and scripts | |
| 2026-10-09 | 1 | Error precedence: `AlreadyPaid` is checked before `WrongRound` (a repeat payment always reports `AlreadyPaid`), and a round beyond the last is rejected (fix in branch `fix/duplicate-contribution-error`) | |
| 2026-10-09 | 9, 13 | Contract tests: randomised invariant tests added (fix branch); 73 tests once the open PRs merge | |
| 2026-10-09 | 1, 2, 6, 8, 9, 10, 13, 14 | Review fixes on #283: error order marked *pending #291* (on main a repeat payment into a filled round still reports `WrongRound`, and a nonexistent round is accepted); files and features from #284, #285 and the fix branch marked "not on main yet"; ID scheme added as an open question (Katlego's review) and flagged in section 1; `CycleNotOpen` maps to neutral `cycle_not_open`; `ERC20InsufficientBalance` mapped (Treasury out of UCTUSD); UCTUSD checked on testnet: re-approve from non-zero is fine, and `burn(uint256)` works from the Treasury (answers the burn-method question, to confirm on #278) | |
| 2026-10-09 | 1, 9, 13 | #291 merged: section 1 error order is now what `main` does (pending markers removed); tests 71 on `main` | |
| 2026-10-09 | 2, 9, 13 | Contract deployed: `StokvelVault` at `0x2f240705314BB79780522635eA47d20072CB8Fe1` (block 8995825), verified on Sourcify; deployment record and `STOKVEL_CONTRACT_ADDRESS` in PR #284; smoke test from the Treasury pending | |

---

## Decisions (agreed; change only via PR)

| # | Decision | Source |
|---|---|---|
| D1 | The whole system moves from XRPL to the XRPL **EVM** Testnet. No XRPL Testnet code remains. Lecturer approval received (Marc, 2026-10-07). | Design session, lecturer approval |
| D2 | One custodial EVM **Treasury Wallet** (the existing term is kept). The database ledger, not separate addresses, tells contribution, pool release and burn movements apart. Whether to add a separate settlement wallet stays open (#207, section 8). | Design session, CONTEXT.md |
| D3 | Users create stokvels and invite other users. The Organiser sets attributes and payout order. The Administrator only has oversight and the global pause. | CONTEXT.md |
| D4 | One contract deployment holds many stokvels (`mapping(stokvelId => Stokvel)`), each with nested cycles and a per-round pool. History is events plus minimal storage (paid, finalised, entitled member). | Design session |
| D5 | Finalise is automatic. Round N releases once every member has contributed to round N+1 **and round N's payout time has passed** (D12). The last round of a cycle releases once every member has contributed to it and its payout time has passed. | CONTEXT.md, team 2026-10-07 |
| D6 | The Stokvel is the remittance **sender**. The pool is paid to the scheduled member's Payout beneficiary through the existing remittance flow. Fee and margin are deducted from the pool. | CONTEXT.md |
| D7 | Contributions are paid from the member's fiat account in the Stokvel currency and refunded as the original fiat amount. The deadline is informational only; there are no penalties on the platform. | CONTEXT.md |
| D8 | A Stokvel has no sending limits. Each contribution counts toward the member's own limits. Joining needs the required KYC standing. | CONTEXT.md |
| D9 | The Stokvel gets a ledger `accounts` row of a new type `STOKVEL` (token currency) and is the sender of its payout remittance. | Team, 2026-10-06 |
| D10 | The "hold the payout until the recipient pays the next round" idea is already covered by D5. The CONTEXT.md rule stays. A per-member early release (release as soon as the recipient alone has paid the next round) is not adopted. | Team, 2026-10-06 |
| D11 | The XRPL variables in `.env` (`XRPL_*`, `PLATFORM_WALLET_*`, `UCTUSD_ISSUER*`) are decommissioned, not removed. | Team, 2026-10-06 |
| D12 | Each round has a **payout time**, set by the Organiser. It is a hard gate: `finalise` reverts before it (brief §7.1). If the payout time passes while a member has not paid, the round stays blocked, not lost, and releases once the last member pays. The contribution **deadline** stays informational (D7). A contract cannot run itself on a date, so a scheduled backend task calls `finalise` for rounds that are due (section 4); the final `contribute` call still triggers the release when the time has already passed. | Team, 2026-10-07 |

## Proposals for product (status: Proposed)

These come from the dev team and need product approval before they are treated as requirements.

| # | Proposal | Why | Status |
|---|---|---|---|
| P1 | **Users create stokvels and invite other users**, instead of a RemitX admin creating them (brief §2 step 1). | Scales better and removes the admin bottleneck. The admin keeps oversight only. | Proposed |
| P2 | **Payout hold to reduce defaulting after payout.** The contract holds a round's pool until the next round is fully paid **and the round's Organiser-set payout time has passed** (D12), so a member who has already been paid cannot stop contributing without blocking everyone. The final round has no next round, so it pays out once everyone has paid it and its payout time has passed. | Mitigates the default risk the brief names. It is the same rule as D5. | Proposed, needs legal review |
| P3 | **Member cap of 3 for the prototype, built to grow.** One constant sets the limit: backend `MAX_STOKVEL_MEMBERS`, and a `maxMembers` value in the contract set at deployment. No fixed-size arrays; round counts are `uint8` (up to 255); cycle length equals the number of members. Raising the limit to 10 or 12 (#197) is a config change. | Brief says three members. Building for more costs little now. | Proposed |
| P4 | **Cancellation.** Ending a stokvel, including partway through a cycle, stops future rounds and refunds unfinalised contributions in the original fiat. Possibly admin-only, on request. | Reverses the brief's "refunds out of scope". | Open (#208) |
| P5 | **Manual admin finalise as a fallback.** Finalisation stays automatic (D5), but the Administrator can also trigger it for a round if the automatic release fails. The contract still enforces the release conditions, so a call on a round that is not ready is rejected (`NotYetFinalisable`). Also gives the demo a natural way to show a blocked finalisation. | Restores the brief's admin finalise (§7.3) as a safety net. Covers a failed trigger only, not a paused contract or RPC outage. | Proposed |
| P6 | **Merge the contribution deadline and the payout time into one date per round.** The build keeps both (deadline informational, payout time a hard gate) because that is the smallest change. | One date is simpler for Organisers and members. | Question for product |

**Legal questions for product (P2):** is a payout that is conditional on a later contribution permitted under South African consumer-protection law and the stokvel exemption from the Banks Act? Trade-off to note: one late payer delays everyone's payout, because every member must have paid before a round releases.

**Stuck rounds (D12, P2):** if a member never pays, the round stays blocked for everyone indefinitely. There are no penalties (D7), so the only way out is cancellation and refunds (P4). Product should see this trade-off, which makes P4 more important.

## Deviations from the brief

The brief (§2, §7, §9) describes one stokvel, three members, an administrator who sets it up and finalises each round, and lists multiple stokvels and refunds as out of scope. This build extends it:

- Many stokvels in one contract, multiple cycles, user-created with invitations (D3, D4, P1).
- A round releases only when fully paid **and** its Organiser-set payout time has passed (D12), matching brief §7.1. The contribution deadline stays informational.
- Finalisation is automatic (D5), with a manual Administrator finalise as a fallback (P5); the brief has the administrator do it every round.
- Refunds on mid-round cancellation (P4).
- TrustMeBank deposits and withdrawals (#202, #203), optional in the brief, are built as required.
- The XRP Ledger is replaced by the EVM chain (D1).

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

**Automatic finalisation (D5, D12):** when a `contribute` call completes round N+1 (or completes the last round) and round N's payout time has already passed, the same transaction releases round N. If everyone paid before the payout time, nothing happens on-chain until the time passes: the backend's scheduled release task (section 4) polls `isFinalisable` and calls `finalise`, once per due round. The final contribution of a cycle can release two rounds at once (the second-last and the last). No person needs to trigger a release; the Administrator can as a fallback (P5), through the backend's operator key.

Uses OpenZeppelin `AccessControl`, `Pausable`, `ReentrancyGuard` and `SafeERC20`. State is updated before every token transfer, and `contribute` and `finalise` are `nonReentrant`.

### Treasury allowance (agreed with the backend, 2026-10-08)

`contribute` pulls the contribution with `safeTransferFrom(msg.sender, vault, contribution)`, so the Treasury Wallet must have approved the vault for UCTUSD first.

- **One-off approval at setup:** the Treasury calls `UCTUSD.approve(STOKVEL_CONTRACT_ADDRESS, type(uint256).max)` once per contract address.
- **Check before each `contribute`:** the worker reads `UCTUSD.allowance(treasury, vault)` and re-approves if it is below the contribution. This also covers a redeploy, because a new contract address needs a new approval.
- **Why not one approval per contribution:** the vault only ever pulls from `msg.sender`, and only `OPERATOR_ROLE` (the Treasury) can call `contribute`, so the allowance can only be spent by Treasury-signed calls. Per-contribution approvals would double the transactions and add nonce ordering without adding protection.
- **Re-approving is safe on UCTUSD:** checked on the testnet (2026-10-09, simulated `eth_call`) that `approve` from a non-zero allowance to a new non-zero amount succeeds. There is no USDT-style "set to zero first" rule. UCTUSD behaves like an OpenZeppelin ERC20.
- **A missing or short allowance** reverts with the token's `ERC20InsufficientAllowance` (from UCTUSD, not the vault). It is a backend fault, not a user error (section 6).

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
| `EVM_TREASURY_ADDRESS` | The Treasury Wallet address |
| `EVM_TREASURY_KEY_ENCRYPTED` | Encrypted Treasury Wallet private key; decryption key held outside the database |
| `EVM_ENCRYPTION_KEY` | Fernet key that decrypts it (as `XRPL_ENCRYPTION_KEY` does today) |
| `MAX_STOKVEL_MEMBERS` | Member cap (3 for the prototype; see P3). Must equal the contract's `maxMembers` |
| `DEPLOYER_PRIVATE_KEY` | **Deployer's local `.env` only** (never `.env.example`, never committed, never on Render). Read only by `contracts/scripts/deploy.ts`; the deployer becomes the contract admin |

The contract deploy script (`npm run deploy:testnet` in `contracts/`; **Pending, not on main yet**, PR #284) reads `EVM_RPC_URL`, `EVM_CHAIN_ID`, `UCTUSD_CONTRACT_ADDRESS`, `EVM_TREASURY_ADDRESS`, `MAX_STOKVEL_MEMBERS` and `DEPLOYER_PRIVATE_KEY` from the repo-root `.env`, with section 2's values as defaults for the public ones.

Keys never appear in the frontend, API responses, logs or git.

---

## 3. Database model (Roles 2 and 3)

> Write first (week-1 deadline). The most important section: backend, frontend and tests all depend on it. Draft; each table needs an ORM model imported in `models/orm/__init__.py`, an Alembic migration, and a row-level-security decision like the ledger tables.

### Tables

| Table | Key columns | Migration |
|---|---|---|
| `stokvels` | `id`, `organiser_user_id`, `name`, `currency` (Stokvel currency), `contribution_amount`, `max_members` (default from config), `status` (`draft`, `active`, `cancelled`), `current_cycle_id`, `account_id` (its `STOKVEL` ledger account), `created_at` | |
| `stokvel_cycles` | `id`, `stokvel_id`, `cycle_number`, `status` (`forming`, `active`, `closed`), `current_round`, `round_count`, `token_contribution_amount` (locked at start), `started_at`, `closed_at` | |
| `stokvel_rounds` | `cycle_id`, `round`, `start_time`, `deadline` (informational), `payout_time` (hard gate, D12) | |
| `stokvel_members` | `id`, `stokvel_id`, `user_id`, `joined_at`, `left_at`, `status` (membership across cycles) | |
| `stokvel_cycle_members` | `cycle_id`, `member_id`, `payout_position`, `payout_beneficiary_id`, `payout_currency`, `continued`, `locked` (per-cycle order and beneficiary, locked once the cycle starts) | |
| `stokvel_invitations` | `id`, `stokvel_id`, `invitee_user_id`, `status` (`pending`, `accepted`, `declined`, `lapsed`), `created_at`, `responded_at` | |
| `stokvel_contributions` | `id`, `cycle_id`, `round`, `member_id`, `amount_fiat`, `amount_token`, `tx_id` (ledger), `onchain_tx_hash`, `block_number`, `status`; UNIQUE (`cycle_id`, `round`, `member_id`) | |
| `stokvel_payouts` | `id`, `cycle_id`, `round`, `member_id`, `release_status`, `quote_id`, `remittance_id`, `release_tx_hash`, `burn_tx_hash`; UNIQUE (`cycle_id`, `round`) | |
| `stokvel_sync_state` | `id`, `last_processed_block`, `updated_at` (cursor for `stokvel.sync_events`; proposed, ticket R2-13) | |

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

_The brief's wording of the remittance statuses (`created → burning → burnt → credited`) differs from the existing ledger states. Recommendation: keep the ledger states, because the ledger already uses them and switching to the brief's names would likely need several changes. Product to confirm before the frontend depends on either._

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
| `stokvel.release_due_rounds` | none (beat) | Celery beat | Finds rounds whose payout time has passed and whose paid condition holds but are not yet released, and queues `stokvel.release_pool` for each. Idempotent: the claim guard and the contract's `AlreadyFinalised` stop a double release (D12) |
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
| `POST /admin/stokvel-contract/pause` and `/unpause` | Administrator | Emergency stop and resume. Pause takes a required `reason` in the request body |
| `POST /admin/stokvels/{id}/rounds/{n}/finalise` | Administrator | Manual fallback if automatic finalisation fails (if P5 is approved). Audit-logged. A round that is not ready returns 409 `round_not_finalisable` |
| `POST /admin/stokvels/{id}/cancel` | Administrator | Cancel (if P4 is approved). Takes a required `reason` in the request body |

### Audit log of admin actions

Admin actions on stokvels are recorded in the **existing** audit log (`audit_log`, written only through `audit_service.record_audit`, append-only, read through `GET /admin/audit` with `audit:read`). No new table is needed: action strings are free text in the database, and the `AuditAction` and `AuditSubject` enums in `models/orm/audit_log.py` gain new members. The entry is staged in the same transaction as the action, as for every other audit entry, and never contains PII: ids, round numbers, statuses and transaction hashes only.

| Admin action | Audit action (proposed) | Subject type | Subject id | Recorded in `before` / `after` |
|---|---|---|---|---|
| Pause the contract | `stokvel.contract.paused` | `stokvel_contract` | a fixed constant id (like `AUDIT_LOG_INDEX_SUBJECT_ID`) | paused flag; `reason` required |
| Resume the contract | `stokvel.contract.unpaused` | `stokvel_contract` | same constant | paused flag |
| Manual finalise (P5) | `stokvel.round.finalised_manually` | `stokvel` | stokvel id | cycle, round, release status, transaction hash if known |
| Cancel a stokvel (P4) | `stokvel.cancelled` | `stokvel` | stokvel id | stokvel status, number of contributions queued for refund; `reason` required |

- Only actions by a real staff member are logged here (`actor_user_id` is never null). The automatic release, event sync and refund tasks are system actions; their trail is the ledger, `stokvel_payouts` and the contract events.
- To show only stokvel entries, filter `GET /admin/audit` by `subject_type=stokvel` or `stokvel_contract`; an optional `action_prefix=stokvel.` filter is suggested so one call returns both.
- The admin audit page gets a stokvel filter (R4-12).

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

_Roles 1, 2 and 4 to confirm codes and wording._

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
| One Treasury Wallet, or a separate settlement wallet for pool release (#207)? D2 chooses one wallet; the wallet has been created. Confirm | Open | Role 1, Product | |
| Burn method (#206): does UCTUSD have a `burn()` function, or do we transfer to a dead address? Check the token on the explorer | **Answered, to confirm on #278 (R1-07):** the token has `burn(uint256)` and `burnFrom`, and `burn(amount)` called by the Treasury succeeds (simulated on the testnet, 2026-10-09). No dead-address transfer is needed | Role 1 | |
| Contract IDs: pack the database UUID into `bytes32` (current section 1), or give each stokvel and member a separate generated `bytes32` ID (Katlego, #283 review)? The contract accepts either. Packing needs no extra column and lets event sync map an ID straight back to its row; a separate ID keeps on-chain IDs unrelated to the database | Open: asked Marc (@marclevin). Recommendation for the MVP: packed UUID | Roles 1, 2 | |
| Contribution amount: fixed token amount or fixed fiat amount? If a fixed token amount, live exchange rates must be taken into account (proposal: member debit = token amount × live rate at contribution). Refunds return the original fiat amount entered | **Contract side resolved (2026-10-09):** a fixed UCTUSD amount set in `createStokvel` for all cycles, confirmed by the backend; a new amount means a new stokvel (MVP). Still for product: the fiat debit rule (live rate at contribution) | Product, Roles 2, 3 | |
| Per-cycle contribution amounts (move the amount into `startCycle`, so the Organiser can change it between cycles)? | Deferred: not in the MVP (2026-10-09). An interface change and a redeploy if wanted later | Role 1, Product | |
| Admin (deployer) key for pause and unpause on the server: R3-07 (#244) must sign `pause()` with the **admin** key, not the Treasury key, and #277 does not cover storing it. Store it the same way as the Treasury key, or keep pause as a manual step run by the key holder? | Open | Roles 1, 3 | |
| New `STOKVEL_REMITTANCE` type, or reuse the existing remittance legs with the stokvel account as sender (this doc's recommendation)? | Open | Roles 2, 3 | |
| Cancellation (P4): who may cancel, and does it reverse the brief's "refunds out of scope"? (#208) | Open | Product | |
| Do fee and margin come out of the pool or from members? CONTEXT.md says the pool (D6) | Confirm | Product | |
| Are the fee and margin taken from the pool converted back to fiat, and if so how? Suggestion: convert them to fiat at finalisation and deduct them from the pool before the payout, so beneficiaries receive their payout in fiat after fees | Open, product decision | Product | |
| Contribution deadline informational only, with no penalties on the platform (D7)? | Confirm | Product | |
| Stokvel has no sending limits, but each contribution counts toward the member's own limits (D8)? | Confirm | Product | |
| Treasury key storage: the encrypted key sits in `.env` rather than a database column (as the wallet seed does today). Acceptable? | Confirm | Product | |
| Approve P5 (manual admin finalise fallback)? | Open | Product | |
| Merge the contribution deadline and payout time into one date per round (P6)? | Open | Product | |
| Stuck round if a member never pays: accept it, relying on cancellation (P4) as the exit? | Open | Product | |
| Should an admin's look at a stokvel's member data (for oversight) also be logged, as KYC reads are? | Open | Product, Role 5 | |
| PR #211's log redaction also hides EVM transaction hashes in logs (they look like keys) until exact-value redaction lands in #204. Acceptable for debugging and the demo? | Open | Role 2, Role 6 | |
| Demo timing: payout times a few minutes apart, and how to show a stuck round | Deferred | Role 6 | |
| Legal status of P2 (payout conditional on the next contribution) | Open | Product | |
| Remittance status names: brief's `created → burning → burnt → credited` vs existing ledger states. Recommendation: keep the ledger states (fewer changes) | Open, product to confirm | Product, Roles 2, 3 | |
| Row-level security for the new stokvel tables | Open | Roles 2, 3 | |
| Seeder and load test: update stories and `tools/loadtest/fake_xrpl_worker.py` for EVM | Open | Role 6 | |

Resolved: finalisation is automatic (D5); a manual admin finalise is kept as a fallback, pending approval (P5).

Resolved (2026-10-08): the Treasury approves the stokvel contract once per contract address (`approve(vault, max)`), and the worker checks the allowance before each `contribute` (section 1, "Treasury allowance"). Backend confirmed sections 1 and 6.

---

## 9. Implementation progress

Milestones (Katlego-Sekoele/RemitX): *EVM wallet setup and switch over*, *Bank API Integration and Bank Deposit simulation switch over*, *Smart Contract Creation and Connection*.

| Step | Status | Issues | Notes |
|---|---|---|---|
| Replace the XRPL layer with EVM | In progress | #276 (was #204) | See "EVM switch-over" below. PR #211 (open) adds the worker-only key loader in `evm_service.py` and the `web3` dependency; sending transactions, the burn and the XRPL removal remain |
| Treasury Wallet as EVM address, encrypted key | In progress | #277 (was #205) | PR #211 (open, not merged): wallet creation script, worker-only key loader, log redaction, extended gitleaks rule and leak tests. Still open: operator role at deployment (#218), UCTUSD funding, and recording the address in section 2 |
| Burn UCTUSD on EVM | Not started | #278 (was #206) | Needs burn-method answer |
| Contract: stokvels and cycles, interface (DEC-1) | Done | #197, #212, #215 | Merged in PR #282 (2026-10-08); #279–#281 closed as superseded. Matches section 1 and D12 |
| Contract: contributions and finalisation | Done | #198, #212 | Merged in PR #282: payout-time gate (D12), external `finalise` |
| Contract: pause and resume | Done | #217 (was #199) | Merged in PR #282 (contract only; backend route is R3-07 #244, admin control R4-07 #256) |
| Contract tests | Done | #216 (was #200) | 71 on `main`: hand-written tests for every rule plus randomised invariant tests (80 runs × 60 steps against a reference model), from #282 and #291. PR #285 adds the coverage fixes and the ABI drift test (73; 100% lines, 99% branches) |
| Contract testnet deployment | Deployed (smoke test pending) | #218 | Deployed 2026-10-09 at `0x2f24…8Fe1` (section 2) from the fixed contract (#291); all post-deploy checks passed; verified on Sourcify. Record and `.env.example` in PR #284 (open). Closes when a `contribute` from the Treasury Wallet succeeds on testnet (Role 2 holds the key; needs `createStokvel`, `startCycle`, `approve`, `contribute`) |
| Contract README, ABI export, ADR | In review | #219 | PR #285: `contracts/README.md`, `contracts/abi/StokvelVault.json` (the ABI the backend loads), `docs/adr/0002-one-contract-many-stokvels.md` |
| Contract member cap (DEC-3) | Contract side done | #213 | `maxMembers` = 3 at deployment. Backend `MAX_STOKVEL_MEMBERS` and ticket wording remain |
| Contract cancel and refund | Blocked | #220 | Waits on #208 |
| Backend connection to the contract | Not started | #273 (was #201) | |
| Members create stokvels and invite others | Not started | #229 (was #209) | |
| DB models and migrations | Not started | | Section 3 |
| Worker tasks | Not started | | Section 4 |
| API routes | Not started | | Section 5 |
| Stokvel audit log (admin actions) | Not started | | Section 5, "Audit log of admin actions" |
| Frontend screens | Not started | | Member, Organiser, invitations, admin pause |
| TrustMeBank deposits and withdrawals | Not started | #274, #275 (were #202, #203) | Required in this build (optional in the brief) |
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
2. **Contract** (#197–#200, now #212–#220): Hardhat project in `contracts/` (done, PR #282), tests per brief §7.5 (done), deploy and record the address in section 2 (#218, in progress).
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
| Docs | [CLAUDE.md](../CLAUDE.md) (hard constraint says "XRPL Testnet only"; RLUSD wording), [Transaction_Flow_Context.md](Transaction_Flow_Context.md), [DEPLOYMENT.md](DEPLOYMENT.md), `project-brief.md`; add ADRs for single contract with many stokvels (written in PR #285, not on main yet: `docs/adr/0002-one-contract-many-stokvels.md`), the `STOKVEL` ledger account, and the single Treasury Wallet; add "Cancellation" to CONTEXT.md if P4 is approved |

## 10. Features added

_Add one entry per feature as it lands: what it does, who owns it, PR link._

| Feature | What it does | Owner | PR |
|---|---|---|---|
| Stokvel contract (`StokvelVault`) | One contract for every stokvel: create stokvels, start cycles (members, schedule), contributions filled in order, automatic release and `finalise` under D5 and D12, admin pause and resume, member cap set at deployment. 69 tests | Kerry (Role 1) | #282 (merged) |
| Contract deploy script | `npm run deploy:testnet`: deploys with admin = deployer, operator and release target = Treasury Wallet, UCTUSD, `maxMembers` 3; checks settings, token, gas and roles; records the deployment | Kerry (Role 1) | #284 (open, not on main yet) |
| Contract ABI for the backend | `contracts/abi/StokvelVault.json`, regenerated by `npm run export:abi`; a test fails if it drifts from the contract | Kerry (Role 1) | #285 (open, not on main yet) |

## 11. How things are connected

```
Frontend → API route → controller → ledger legs (pending) → queue
       → worker (web3.py) → stokvel contract → event → sync task → database
```

- **Contribution:** the member's fiat account is debited (counts toward their limits), the platform converts the amount to UCTUSD, and the worker sends it from the Treasury Wallet to the contract with `contribute`. The contribution is `confirmed` only after the on-chain event.
- **Finalisation:** when every member has paid round N+1 (or everyone has paid the last round) **and the round's payout time has passed**, the contract releases round N's pool to the Treasury Wallet. The database credits the stokvel's `STOKVEL` ledger account.
- **Payout:** the stokvel is the sender. A quote and remittance are created from the stokvel account to the scheduled member's Payout beneficiary, using FSE's fee and margin, deducted from the pool. The existing settlement chain burns the UCTUSD and credits the beneficiary's payout-currency account. The burn hash, beneficiary credit and remittance reference are stored together.
- **No bridge:** nothing moves on the XRP Ledger; the remittance step produces the quotation, record and reference, and the burn stands for the simulated cash-out.

## 12. User flow

1. A KYC-approved user creates a stokvel (name, Stokvel currency, contribution, start time, deadlines and a payout time per round).
2. The Organiser invites users by account reference. Only KYC-approved users with a fiat account in the Stokvel currency can be invited. Nobody is a member until they accept.
3. The Organiser sets the payout order.
4. Each member chooses a Payout beneficiary and payout currency (the account must already exist).
5. The Organiser starts the cycle once at least two members are ready. Invitations not yet accepted lapse. Membership, order and beneficiaries are now locked.
6. Each round, every member contributes before the deadline (informational only).
7. The contract finalises automatically once the round is fully paid and its payout time has passed (a scheduled task releases it if everyone paid early); the payout remittance goes to the scheduled member's beneficiary; the member sees status, hashes and the remittance reference.
8. After the last round the cycle closes. Each member chooses to continue or leave, and may change their beneficiary; a new cycle can then start.

## 13. Files created

| File | Purpose | Added in |
|---|---|---|
| `docs/stokvel_integration.md` | This tracking document | |
| `contracts/` (Hardhat 2, Solidity 0.8.24, OpenZeppelin v5) | Contract project; `npm ci && npx hardhat test` | #282 |
| `contracts/src/StokvelVault.sol` | The stokvel contract (section 1) | #282 |
| `contracts/test/` | Tests: setup, contribute, pause, views, randomised invariants (on main), ABI drift (#285, open); `helpers.ts` has the fixtures and `uuidToBytes32`, the reference ID packing | #282, #291, #285 |
| `contracts/src/mocks/` | Test-only tokens (`MockUCTUSD`, `ReentrantToken`, `FeeOnTransferToken`); never deployed | #282 |
| `contracts/smart_contracts_changes.md` | Per-ticket log of contract changes and decisions | #282 |
| `contracts/hardhat.config.ts` | Compiler settings (on main, #282); `xrplEvmTestnet` network, explorer verification and `.env` loading (#284, open) | #282, #284 |
| `contracts/scripts/deploy.ts` | Deploy script (`npm run deploy:local`, `npm run deploy:testnet`) | #284 (open, not on main yet) |
| `contracts/deployments/xrplEvmTestnet.json` | Deployed address, block, tx hash and constructor arguments (written by the deploy script) | #284 (open, not on main yet) |
| `contracts/scripts/verify-sourcify.js` | Verifies the recorded deployment on Sourcify v2 (`npm run verify:sourcify`); the explorer's verifier lacks solc 0.8.24 | #284 (open, not on main yet) |
| `contracts/abi/StokvelVault.json` | Exported ABI the backend loads | #285 (open, not on main yet) |
| `contracts/scripts/export-abi.js` | Writes the ABI from the build (`npm run export:abi`) | #285 (open, not on main yet) |
| `contracts/README.md` | Contract overview: trust assumption, rules, roles, IDs, backend usage, deploy | #285 (open, not on main yet) |
| `docs/adr/0002-one-contract-many-stokvels.md` | ADR for D4 (one contract holds every stokvel) | #285 (open, not on main yet) |

## 14. Functions created

| Function | File | Purpose | Added in |
|---|---|---|---|
| `createStokvel`, `startCycle`, `contribute`, `finalise`, `pause`, `unpause` | `contracts/src/StokvelVault.sol` | Contract interface (section 1) | #282 |
| `getStokvel`, `getCycle`, `hasPaid`, `roundPool`, `isFinalisable`, `isMember`, `paidCount`, `openRound` | `contracts/src/StokvelVault.sol` | Contract views (section 1) | #282 |
| `uuidToBytes32` | `contracts/test/helpers.ts` | UUID → left-aligned `bytes32`; the backend's helper must match | #282 |
| `npm run deploy:local`, `npm run deploy:testnet` | `contracts/scripts/deploy.ts` | Dry run on a local chain; deploy to the XRPL EVM Testnet | #284 (open, not on main yet) |
| `npm run export:abi` | `contracts/scripts/export-abi.js` | Compile and write `contracts/abi/StokvelVault.json` | #285 (open, not on main yet) |
