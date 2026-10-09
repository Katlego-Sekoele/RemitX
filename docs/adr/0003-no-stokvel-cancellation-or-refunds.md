# A stokvel cannot be cancelled mid-cycle, and contributions are never refunded

A stokvel cannot be cancelled once a cycle has started, and no contribution is
refunded (decision #208, 2026-10-09). The brief (§9) lists refunds as out of
scope, and cancellation (P4 in the integration doc) was proposed as an
extension. Building it needs a cancelled state and a refund function in the
contract, a refund path through the ledger back to fiat that is safe to retry,
an admin route and screen, and their tests. That is too much risk for the time
left, so the product decision is to keep the brief's position. A possible
future design is written down in
[stokvel_product_deviations.md](../stokvel_product_deviations.md), "Future
extension: cancellation and refunds".

## Consequences

- A round blocked by a member who never pays stays blocked. There is no
  on-platform way out; members settle it among themselves. The demo shows the
  blocked round, as the brief asks.
- The UCTUSD paid into a blocked round stays locked in the contract, and that
  stokvel can never start another cycle (`startCycle` reverts with
  `CycleInProgress`). Its members start a new stokvel instead.
- The contract has no `cancel` or `refund` functions and no
  `StokvelCancelled` or `ContributionRefunded` events. The backend has no
  `stokvel.refund` task, no `stokvel_refund` transaction type and no cancel
  route. R1-06 (#220) and R3-09 (#246) are dropped.
- Pause (#217) is the only emergency control, and it never moves funds.
- Adding cancellation later is additive: a new contract function and event, a
  new task and a new transaction type. The existing release and settlement
  paths do not need to change.
