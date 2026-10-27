# RemitX Stokvel

A cross-border remittance platform (FSE) extended with a rotating stokvel: members pool contributions in a smart contract, and each round's pool is paid out as a remittance to the scheduled member's beneficiary abroad.

## Language

### Stokvel

**Stokvel**:
A group of members who contribute a fixed amount each round and receive the pooled funds in turn. Created by a platform user, it persists across cycles and can run more than one. Many stokvels exist on the platform at once.
_Avoid_: Group, cohort

**Organiser**:
The **Member** who created a **Stokvel**. They create the stokvel, set its attributes and invite other users. They do not release rounds.
_Avoid_: Owner, admin, creator

**Administrator**:
A platform operator with oversight of all stokvels. Distinct from an **Organiser**; has no role in running any one stokvel. Can pause and resume the whole stokvel contract as an emergency stop, which halts contributions, finalisation and refunds for every stokvel but never bypasses their conditions.
_Avoid_: Admin (ambiguous with Organiser)

**Member**:
A platform user who belongs to a **Stokvel**, contributes each round and receives one **Payout** per **Cycle**. Must hold the required KYC standing to join.
_Avoid_: Participant, contributor

**Invitation**:
A **Stokvel** creator's request that another platform user join as a **Member**. Joining happens only between cycles, never partway through one. An invitation that has not been accepted when the **Organiser** starts a **Cycle** lapses, and its recipient is not a member of that cycle. The **Organiser** may revoke an invitation while it is pending.
_Avoid_: Invite link, request

**Cycle**:
One full run of a **Stokvel** in which every member receives exactly one payout, ending after the last round. Its length equals the number of members who continued into it, and needs at least two. Membership is fixed for the duration of a cycle. Started manually by the **Organiser**, who may start it as soon as at least two members are ready; members who have not accepted an **Invitation** or confirmed **Continuation** by then are not in it.
_Avoid_: Term, season

**Round**:
One contribution period of a **Cycle**, in which every member contributes and one member's payout is released.
_Avoid_: Period, turn

**Stokvel currency**:
The fiat currency a **Stokvel** is denominated in, set by the **Organiser**. Every **Contribution** is paid from the member's fiat account in this currency.
_Avoid_: Contribution currency

**Contribution**:
A **Member**'s payment into a **Round** of a fixed **UCTUSD** amount (the same for every round and cycle of the **Stokvel**), paid from their fiat account in the **Stokvel currency** at the live rate when they contribute, and held by the stokvel contract. Counts toward the member's own sending limits, but only the monthly limit can refuse it, never the daily one; a **Stokvel** has none. Joining needs room left in the month for one contribution.
_Avoid_: Deposit (that is a ZAR cash-in), payment

**Payout order**:
The sequence in which **Members** receive their **Payout** across the rounds of a **Cycle**. The members agree it among themselves off the platform; the **Organiser** enters it before each cycle, and it is fixed once the cycle starts. The platform never chooses the order.
_Avoid_: Rotation, queue

**Payout beneficiary**:
The FSE beneficiary, together with the payout-currency account of theirs, that a **Member** nominates to receive their **Payout** for a **Cycle**. The payout account must already exist, and a cycle cannot start until every member has one. Chosen before each cycle, either kept from the previous one or changed, and locked once the cycle starts.
_Avoid_: Recipient

**Start time**:
The moment a **Round** opens for contributions, set by the **Organiser**.

**Deadline**:
The time by which **Members** are expected to contribute to a **Round**, set by the **Organiser** and shown to every member. It is informational only: the platform does not enforce it or penalise anyone, and a late contribution is still accepted. Consequences are for the members to handle off-platform.
_Avoid_: Cut-off, due date

**Payout time**:
The date and time from which a **Round**'s **Pool** may be released, set by the **Organiser** for each round and no earlier than its **Deadline**. Unlike the deadline it is enforced: a round is never released before it. A member who has not paid by then can still pay; the round waits for them. Whether to merge the deadline and the payout time into one date is an open question (P6 in the stokvel integration doc).

**Pool**:
The sum of all members' contributions in a **Round**, released as one amount to that round's scheduled member.
_Avoid_: Pot, kitty, payout amount

**Finalise**:
To release a **Round**'s **Pool** and record the member it is owed to. A round is finalised once its **Payout time** has passed and every member has contributed to the next round; the last round of a **Cycle**, having no next round, is finalised once its payout time has passed and every member has contributed to it. Happens automatically; no person triggers it.
_Avoid_: Release, close

**Continuation**:
A **Member**'s choice, once a **Cycle** ends, to stay in the **Stokvel** for the next cycle or to leave.
_Avoid_: Renewal, opt-in

**Payout**:
The cross-border remittance a member receives from a finalised **Pool**, paid in full. The FSE remittance fee and margin on it are paid by the **Members** on top of their contributions, each paying an equal share, so nothing is deducted from the pool.
_Avoid_: Disbursement

### Tokens

**UCTUSD**:
The ERC-20 token on the XRPL EVM Testnet that stands in for RLUSD. Members' contributions, the stokvel contract's holdings and every remittance's settlement are all in UCTUSD.
_Avoid_: uctusd, EVMuctusd, RLUSD (a real asset we don't use)

### Wallets

**Treasury Wallet**:
The platform's custodial address on the XRPL EVM Testnet that holds **UCTUSD** on RemitX's behalf, sends contributions to the stokvel contract and burns UCTUSD at settlement.
_Avoid_: Platform wallet, EVM Wallet, settlement wallet

### Remittance

**Sender**:
The party a **Quote** and **Remittance** are made for, whose fiat is converted and paid out. For a stokvel **Payout**, the sender is the **Stokvel**.
_Avoid_: Payer, remitter

**Beneficiary**:
A registered platform user whom a sender nominates to receive a remittance, paid into their account in a chosen payout currency.
_Avoid_: Recipient, payee, contact

**Quote**:
The frozen price of one remittance (amount, fee, margin, rates, receiver amount), valid for a short time and usable once.
_Avoid_: Estimate, offer

**Remittance**:
A confirmed **Quote** settled by moving the sender's value to the **Beneficiary** through a set of ledger legs, only final once the **Burn** is confirmed.
_Avoid_: Transfer, payment

**Fee**:
What FSE charges on a **Remittance**: a fixed amount plus a percentage of the sender amount.
_Avoid_: Charge, commission

**Margin**:
The percentage FSE keeps on a **Remittance**'s exchange rate, separate from the **Fee**.
_Avoid_: Spread, markup

**Burn**:
The on-chain destruction of the **UCTUSD** a remittance used, taking it back out of the **Treasury Wallet**. It is the only on-chain leg, and nothing confirms until it does.
_Avoid_: Redemption

### Ledger

**Account**:
A ledger holder of one currency's balance: a user's, or one of the platform's own (bank, fee revenue, treasury). A **Stokvel** also holds one.
_Avoid_: Wallet (that is on-chain), balance

**Transaction**:
One ledger row moving an amount from one **Account** to another, in one of the pending, processing, confirmed or failed states. Not a **Contribution** or **Payout**, each of which is made of several.
_Avoid_: Transfer, payment

**Deposit**:
Fiat paid into the platform's bank account and credited to a user's fiat **Account**, now authorised through **TrustMeBank**.
_Avoid_: Contribution, top-up, cash-in

**Withdrawal**:
Fiat moved from a user's **Account** to a verified bank account of theirs.
_Avoid_: Cash-out, payout (that is a stokvel **Payout**)

**TrustMeBank**:
The mock bank whose authorised payments stand in for real fiat movement into and out of the platform.
_Avoid_: Bank API, mock bank

### Compliance

**KYC standing**:
A user's verified identity level, tier and risk rating, which sets whether they may send or join a **Stokvel** and their daily and monthly sending limits.
_Avoid_: Verification status, KYC level

