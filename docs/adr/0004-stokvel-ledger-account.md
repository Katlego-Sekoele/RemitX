# A stokvel has its own ledger account

Every movement of money in RemitX is a row in `transactions` between two
`accounts` rows. A stokvel's money moves too: members contribute into it, the
contract releases a round's pool, and the pool is paid out as a remittance
with the stokvel as sender (D6). So each stokvel gets one `accounts` row of a
new type, `STOKVEL`, in the token, linked from `stokvels.account_id`. This is
decision D9 in `docs/stokvel_integration.md`.

## Considered options

- **No account: book the pool straight from the members or the Treasury
  Wallet to the beneficiary.** No schema change, but a released pool would
  sit nowhere in the ledger between release and payout, the payout remittance
  would have no sender account, and nothing could show what a stokvel holds.
- **A platform account shared by every stokvel.** One row, but the ledger
  could no longer tell one stokvel's pool from another's; that would need a
  side table, which is what an account already is.
- **One account per stokvel (chosen).** The pool is visible per stokvel, the
  payout reuses the existing remittance legs with the stokvel account as
  sender, and reconciliation can compare each account with the contract.

## Consequences

- `accounts_type_valid` allows `STOKVEL`. A `STOKVEL` row has no user and no
  reference, which the existing owner and reference CHECKs already allow for
  any type but `USER`.
- `accounts_stokvel_balance_nonneg`: a stokvel pays out only what its members
  put in, so its balance never goes below zero (unlike the platform accounts,
  where the issuer's goes negative by design).
- A `STOKVEL` account is not a platform account: it is left out of
  `AccountRepository.list_platform_accounts`, and so out of the admin
  platform-accounts view and the treasury coverage figure.
- Its label is `Stokvel <id>`, never the stokvel's name, so it can never
  collide with a platform account's label, which services use as a lookup key.
- `quotes.sender_user_id` becomes nullable, with `quotes.stokvel_id` naming a
  stokvel sender and a CHECK that exactly one is set. Row-level security on
  `quotes` matches on `sender_user_id`, so a customer does not see a stokvel's
  quote through it; the member screen (R2-14) has to provide that view. The
  proposed fix (pending approval; task on #236) extends the ledger policies
  with `stokvel_is_member` and leaves `sender_user_id` NULL, so a payout never
  counts toward a member's limits.
- The transfer reads outer-join the sender user, so a stokvel's payout still
  lists for its recipient and in the admin totals, with no counterparty user
  or name.

## Update (2026-10-16, R2-11): what the account holds

Agreed with R3-01's owner when the contribution API was built. Contributions
book into the account as they are made, and a release books out of it:

| Step | Ledger | On-chain |
|---|---|---|
| Contribution | member fiat -> RemitX bank; Treasury Wallet -> `STOKVEL` | Treasury -> contract |
| Pool release | `STOKVEL` -> Treasury Wallet | contract -> Treasury |
| Payout | Treasury -> `STOKVEL` -> beneficiary token -> Treasury -> burn | burn |

- The `STOKVEL` balance is therefore the stokvel's **unreleased pools in the
  contract**, not a released pool waiting for its payout, as first written.
  Reconciliation compares it with the contract's pools for that stokvel.
- A pool is counted once: the release takes it out of the account, and the
  payout passes it through on the way to the beneficiary. No separate account
  for "tokens held by the contract" is needed.
- `accounts_stokvel_balance_nonneg` still holds: a release never takes out
  more than the contributions put in.
- Members see and record legs on their stokvel's account through the
  `transactions` policy (`stokvel_account_is_member`, migration
  `V20261016_1500`), the ledger part of the proposed fix above. The quote and
  remittance parts are still pending.

