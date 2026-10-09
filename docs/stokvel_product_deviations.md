# Stokvel: deviations and suggestions for product

## Needs product approval

| # | Proposal | Why | Question for product |
|---|---|---|---|
| P1 | Users create stokvels and invite others, instead of an admin creating them (brief §2 step 1). The admin keeps oversight. | Removes the admin bottleneck and scales better. | Approve? |
| P2 | Payout hold: a round's pool is released only once every member has paid the next round **and** the round's payout time (set by the Organiser) has passed. The last round releases once everyone has paid it and its payout time has passed. | Reduces the risk that a member who has been paid stops contributing. | **Legal review.** Is a payout conditional on a later contribution allowed under SA consumer-protection law and the stokvel exemption from the Banks Act? One late payer delays everyone's payout, and if a member never pays the round stays blocked until they do (no penalties, and no cancellation since P4 was rejected). |
| P3 | Member cap of 3 for the prototype, built to grow. One config value sets it, so moving to 10 or 12 is a config change. | The brief says three members, and building for more now costs little. | Confirm 3 for the prototype. |
| P4 | Cancellation: end a stokvel, including mid-cycle, and refund unfinalised contributions in the original fiat. Possibly admin-only. | Reverses the brief's "refunds out of scope". | **Decided 9 Oct: out of scope, not built** (#208, [ADR 0003](adr/0003-no-stokvel-cancellation-or-refunds.md)). See "Future extension: cancellation and refunds" below. |
| P5 | Manual admin finalise as a fallback if the automatic release fails. The contract still rejects it if the round isn't ready. | Restores the brief's admin finalise (§7.3) as a safety net, and lets the demo show a blocked finalisation. | Approve? |
| P6 | Merge the contribution deadline and the payout time into one date per round. The build keeps both: the deadline is informational, and the payout time is the hard gate. | One date is simpler for Organisers and members. | Merge, or keep both? |

## Deviations from the brief

1. Many stokvels and multiple cycles in one contract, user-created with invitations. Brief §9 lists multiple stokvels as out of scope.
2. Finalisation is automatic by default (brief §2 step 4 has the administrator do it). **Suggested (P5): keep a manual admin finalise as a fallback** in case the automatic release fails. The contract still enforces the release conditions, so an admin call on a round that isn't ready is rejected. This also gives the demo a natural way to show a blocked finalisation. If approved, the admin screen has finalise, pause and resume, as in brief §7.3.
3. Finalisation is triggered automatically once the next round is fully paid and the payout time has passed.
4. The XRP Ledger is replaced by the XRPL EVM Testnet. The brief required XRPL, so this needs the lecturer's approval. Marc approved it on 7 Oct.
5. Remittance status names: the brief says `created → burning → burnt → credited`, while the ledger uses `pending → processing → confirmed | failed`. One set must be chosen before the frontend depends on it. Which one to choose? The ledger already uses the latter, so switching to the brief's naming convention would most likely require several changes. Product to confirm.
6. A stokvel entity gets its own ledger account type (`STOKVEL`) and is the sender of its payout remittance (D6, D9).
7. Beneficiary and payout currency are chosen per member and per cycle. The picker reuses the existing beneficiary contact list screen, as the brief asks.
8. Unaccepted stokvel invitations lapse when the Organiser starts the cycle.
9. TrustMeBank deposits and withdrawals are optional in the brief but are built as required.

## Other suggestions and decisions to be made

- **Contribution amount:** fixed token amount, or fixed fiat amount? If a fixed token amount, live exchange rates need to be taken into account. Product to confirm.
- **Fees:** Should fee and margin costs come out of the pool, or from members (D6)? **Product decision needed:** are the fee and margin taken from the pool converted back to fiat, and if so how? A suggestion would be to convert the fee and margin to fiat at the time of finalisation, and then deduct it from the pool before distributing the payout. This would ensure that beneficiaries receive their payouts in fiat after fees are accounted for.
- **Deadlines and penalties:** Should the contribution deadline be informational only? With no penalties on the platform (D7)? Product to confirm.
- **Limits:** a stokvel has no sending limits, but each contribution counts toward the member's own limits (D8). Product to confirm.
- **Audit log:** admin actions on stokvels (pause, resume, manual finalise) are recorded in the platform's existing audit log, with the reason where one is required. Automatic actions are not admin actions and are traced through the ledger and contract events. Product to confirm whether an admin's look at a stokvel's member data should be logged too.
- **Single wallet:** one Treasury Wallet, with the ledger telling movements apart, rather than a separate settlement wallet. Tech has made the wallet.
- **Treasury key storage:** the encrypted key sits in `.env` rather than a database column, as the wallet seed does today. Product to confirm.
- **Product journey:** the frontend lead needs to meet with product to collect the user journey (R4-01) and agree on the list of screens to be added.

## Future extension: cancellation and refunds

**Status: out of scope, not built** (decided 9 Oct, #208, [ADR 0003](adr/0003-no-stokvel-cancellation-or-refunds.md)). The brief (§9) lists refunds as out of scope, and the team chose to keep that position rather than take on the extra contract, ledger and screen work. This section records how it could be added later, so the work is not lost.

**What happens without it.** A stokvel cannot be cancelled once a cycle starts, and no contribution is refunded. If a member never pays, their round stays blocked for everyone (D12, P2). The money already paid into that round stays locked in the contract, and the stokvel cannot start another cycle, so its members would start a new one. The members settle the shortfall among themselves, off the platform. The demo shows the blocked round, as the brief asks.

### How it could work

1. **Who can cancel.** The Administrator only, at a member's request, with a required reason that goes to the audit log. Letting the Organiser cancel on their own would let one person unwind everyone's savings.
2. **What cancelling does.** It stops all future rounds and contributions for that stokvel. A cancelled stokvel cannot restart; members create a new one.
3. **What is refunded.** Every contribution to a round that has not been paid out goes back to the member who made it. Rounds already paid out are not refunded.
4. **How much.** The original fiat amount the member paid, credited to the fiat account it came from. Not the token value at the time of cancelling, because the exchange rate may have moved and members should get back exactly what they paid. The platform carries any rate difference.

**Example.** Three members, R500 each. Round 1 was paid out to Sipho. In round 2, Thandi and Lerato paid and Sipho did not. The stokvel is cancelled: Thandi and Lerato each get R500 back in their fiat accounts, Sipho gets nothing back (he paid nothing into round 2), and no further rounds run.

### What it would take to build

| Area | Change |
|---|---|
| Contract | A `cancel(id)` function (operator only) that marks the stokvel cancelled, and a `refund(id, round, memberId)` function that returns one unpaid-out contribution to the Treasury Wallet, once only. Events `StokvelCancelled` and `ContributionRefunded`. Pause also blocks refunds. Tests for cancelling with and without paid-out rounds. Was ticket R1-06 (#220) |
| Ledger | A `stokvel_refund` transaction type, a `cancelled` stokvel status and refund statuses on contributions. The refund converts back to fiat and credits the source account, guarded so a retry never refunds twice |
| Backend | A `stokvel.refund` worker task, and `POST /admin/stokvels/{id}/cancel` with a required `reason`, logged as `stokvel.cancelled`. The event sync marks the stokvel cancelled and queues the refunds. Was ticket R3-09 (#246) |
| Frontend | A cancel action with a reason on the admin stokvel screen, and a "cancelled" state with refund status on the member screen |
| Docs | Add "Cancellation" to CONTEXT.md, and replace ADR 0003 with the new decision |

None of this changes the existing contribution, release or payout paths, so it can be added later without reworking them.

**Questions to answer first:** is the Administrator-only rule right; how a member asks for a cancellation; what happens to a contribution that is still processing when the stokvel is cancelled; and whether a cancelled stokvel's members are told by notification.
