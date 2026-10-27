# Stokvel demo script

The live demo of the stokvel on the QA site, `https://qa.remitx.tech`. Five presenters each show one part of the system, in the order a user meets it. Ticket R6-07 (#272).

Each step has four columns:

- **Do**: what to click. **Bold** words are the exact text on the screen.
- **You'll see**: how you know it worked. Don't move on until you see it.
- **Say**: what to say out loud, in your own words if you like.
- **#**: the step number, so the team can call "step 3.5" during rehearsal.

Rehearse twice. Record the second rehearsal as the backup video.

## Three rules for everyone

1. **Refresh to see changes.** The page only updates by itself for a few seconds after *you* pay. To see someone else's payment or a payout moving, press **refresh** (Mac: ⌘R, Windows: F5). The one exception is in step 3.6.
2. **Wait for "You'll see"** before the next step. Most actions take a few seconds; a payout takes 1 to 3 minutes.
3. **Times are counted from "Start".** "Start" is the moment Person 2 presses **Start cycle** (step 3.3). The payouts happen 5, 10 and 15 minutes after Start, and nothing can move them. Write the real clock times in the run sheet on the day.

## Checklists

### The day before

If any of these is missing, the demo won't work.

- [x] **The QA worker stays awake.** The background worker is what releases the payouts, and it would switch off when idle. **Done:** #391 set the worker to a minimum of 1 instance, applied to QA on 27 Oct. After the demo, a PR sets it back to 0.
- [ ] **The demo users exist on QA**: three verified, funded members and one admin (table below), and the second stokvel, **Siyakhula Savings Club**. The seeder's `demo` scenario creates them all, but it only runs on QA once `tools/seeder/targets.json` lists the QA database. Otherwise create them by hand.
- [ ] **The admin account** has the **compliance officer** role.
- [ ] **Names filled in** in the table below.
- [ ] **Step 2.3 checked**: the Organiser's beneficiary must be a verified user, or the "wrong invite" is refused. If not, use the note under step 2.5.

| Role | Email to sign in with | Real name | Their beneficiary |
|---|---|---|---|
| Organiser | `stokvel.organiser+clerk_test@example.com` | | in Zimbabwe, paid in USD |
| Member 2 | `stokvel.member2+clerk_test@example.com` | | in Namibia, paid in NAD |
| Member 3 | `stokvel.member3+clerk_test@example.com` | | in the US, paid in USD |
| Admin | (the seeded compliance officer) | | none |

Everyone signs in with the code **424242**. There is no password.

### One hour before

- [ ] **Check the platform wallet has enough test money.** From the repo root (needs `EVM_TREASURY_ADDRESS` in `.env`):

  ```bash
  pip install -r platform_wallet/scripts/requirements.txt
  python platform_wallet/scripts/check_balances.py --min-uctusd 40 --min-xrp 5
  ```

  Every line must say PASS. If not, top up: test XRP from the XRPL EVM testnet faucet, and UCTUSD from the lecturer. (The demo uses about 28 UCTUSD. The XRP figure is a guess; adjust it after the first rehearsal.)
- [ ] **The worker is awake**, and the admin's **Stokvels → Contract** page says **Running**.
- [ ] **Five browser windows open and signed in**, one per person (table below). Use a separate browser profile or private window for each, so the sign-ins don't mix.
- [ ] **Slides open** on another screen, for the waits.
- [ ] **15 minutes before Start: Person 3 does step 0.**

### What we must show

Tick each off as it happens. The IDs match `docs/stokvel_test_plan.md`.

- [ ] **D1**: three members, three rounds, each payout reaches the right beneficiary (steps 2.1 to 6.1)
- [ ] **D2**: a round blocked because one member hasn't paid (step 4.5)
- [ ] **D3**: a second payment for the same round is refused (step 3.6)
- [ ] **D4**: an early release is refused (step 5.1)
- [ ] Also: verified members only (1.3), invite and revoke (2.3 to 2.5), the explorer (4.3), the payout reference (4.2), the audit log (5.4)

## Who does what

| Person | Shows | Window | Signed in as |
|---|---|---|---|
| 1 | The platform: sign-in, verification, account, beneficiaries | A | Organiser |
| 2 | Creating the stokvel, inviting, revoking, starting | A | Organiser |
| 3 | The members joining and paying | B and C | Member 2 (B), Member 3 (C) |
| 4 | The payout and the blocked round | A and E | Organiser; the explorer |
| 5 | The admin side | D | Admin |

Window **E** is the explorer page for the stokvel contract:
`https://explorer.testnet.xrplevm.org/address/0x2f240705314BB79780522635eA47d20072CB8Fe1`

With fewer than five people: one person takes 1 and 2, another takes 4 and 5.

## Run sheet

Write the planned Start time here: **Start = ___:___**. Then fill in the clock column (Start minus or plus the minutes).

| When | Clock | Who | What |
|---|---|---|---|
| 15 min before Start | ___:___ | Person 3 | Step 0: start the second stokvel (before the audience arrives) |
| 8 min before Start | ___:___ | Person 1 | Steps 1.1 to 1.5: the platform |
| 5 min before Start | ___:___ | Person 2 | Steps 2.1 to 2.5: create, invite, revoke |
| 3 min before Start | ___:___ | Person 3 | Steps 3.1 and 3.2: members join |
| **Start** | **___:___** | Person 2 | Step 3.3: **Start cycle** |
| Start to 4 min after | ___:___ | Person 3 | Steps 3.4 to 3.7: rounds 1 and 2 paid, and the duplicate |
| **before 5 min after Start** | ___:___ | Person 5 | Step 5.1: the early release is refused |
| 5 min after Start | ___:___ | Person 4 | Steps 4.1 to 4.3: round 1 pays out |
| 8 min after Start | ___:___ | Person 3, then 4 | Steps 4.4 and 4.5: round 3 paid; the blocked round |
| 10 min after Start | ___:___ | Person 5 | Steps 5.2 to 5.4 (round 2 pays out meanwhile) |
| 15 min after Start | ___:___ | slides or questions | Round 3 pays out |
| 17 min after Start | ___:___ | Person 4 | Step 6.1: "3 of 3 paid out" |

## Step 0: the blocked stokvel (Person 3, 15 minutes before Start)

This sets up a second stokvel, **Siyakhula Savings Club**, where one member won't pay. It has to be its own stokvel, because a blocked round stays blocked until that member pays.

| # | Do | You'll see |
|---|---|---|
| 0.1 | Window B (Member 2): **Stokvels** → **Siyakhula Savings Club** → **Open**. In **Start the cycle**, set **How often** to **Every 5 minutes (demo)** → **Start cycle** → **Start cycle** again in the box that pops up | A message that it has started, and the page shows round 1 |
| 0.2 | Wait 30 seconds. Window B: **Pay now** → **Confirm payment** | **Confirming…**, then **Paid** |
| 0.3 | Window C (Member 3): open Siyakhula, refresh, **Pay now** → **Confirm payment** | **Paid** |
| 0.4 | Window B: refresh, then pay again (this is round 2) | **Paid** |
| 0.5 | **Member 3 does NOT pay round 2.** Leave it | |

## Person 1: the platform

Window A. Start on `https://qa.remitx.tech`.

| # | Do | You'll see | Say |
|---|---|---|---|
| 1.1 | **Sign in** with the Organiser's email, code 424242 | **Welcome back, …** | "This is RemitX, a platform for sending money across borders. We've added a stokvel to it: a savings club where everyone pays in each round and one member is paid out, with the money held in a smart contract." |
| 1.2 | Point at the **Balances** card | The rand balance | "Every member is a normal RemitX customer with a rand account." |
| 1.3 | **Profile → Verification** | The **Approved** badge | "Only verified customers can start or join a stokvel. That uses the identity checks the platform already has." |
| 1.4 | **Accounts** → the **South African rand** card. Press the copy button next to **Reference** | **Reference copied** | "Money comes in by bank transfer using this reference. In this demo, payments are simulated: no real money moves." |
| 1.5 | **Beneficiaries** | The Organiser's beneficiary in Zimbabwe | "A beneficiary is someone you send money to in another country. When it's your turn in the stokvel, the money goes to the beneficiary you choose." Then: "Now let's start a stokvel." |

## Person 2: creating the stokvel

Window A, still the Organiser.

| # | Do | You'll see | Say |
|---|---|---|---|
| 2.1 | **Stokvels → New stokvel**. Name: **Demo club**. Currency: **ZAR · South African rand** → **Continue** | The **Amount** step | "Any verified customer can start a stokvel. Everyone pays in the same currency." |
| 2.2 | **Each member pays, per round**: type **40** → **Continue** → **Create stokvel** | **Demo club created**, and the stokvel's page | (While the preview box shows) "Each member pays R40 a round. The fee is paid on top, so the whole pool goes to the beneficiary. Behind the scenes the contract holds this as a test digital dollar called UCTUSD." |
| 2.3 | **Invite members** → **From your beneficiaries**: choose your Zimbabwe beneficiary → **Invite** | **Invitation sent to …** | "Say I invite the wrong person by mistake: this is my mother, who should *receive* my payout, not join." |
| 2.4 | **Invitations** card → **Revoke** next to that name → **Revoke** | **Invitation to … revoked**, and the badge **Revoked** | "Nobody joins until they accept, so I can take an invitation back." |
| 2.5 | **Their ZAR account reference**: type Member 2's reference → **Invite**. Then Member 3's → **Invite** | Two invitations, each **Invited …** | "Now I invite the real members by their account reference." Then: "Over to the members." |

If step 2.3 says **"isn't verified yet"**: skip it. Invite Member 3 in step 2.5, revoke that invitation (step 2.4), then invite Member 3 again.

## Person 3: the members join and pay

Windows B (Member 2) and C (Member 3). The Organiser is a member too: whenever a step says **A**, Person 2 clicks in window A, including step 3.3.

| # | Do | You'll see | Say |
|---|---|---|---|
| 3.1 | B, then C: **Stokvels** (refresh) → the **Invitation** card for Demo club → **Accept** | **You've joined Demo club**, and its page | "The invitation shows who invited them and the cost per round. Accepting makes them a member." |
| 3.2 | B, then C: on the stokvel page, **Your payout** → **Beneficiary**: choose theirs → **Save** | **Your payout goes to …**, badge **Ready** | "Each member picks who gets the money in their round: one in Namibia, one in the US." Then: "Back to the Organiser." |
| 3.3 | **Person 2**, window A: refresh. **Your payout** → choose the Zimbabwe beneficiary → **Save**. In **Start the cycle**: order with the arrows: **Organiser, Member 2, Member 3**. **How often**: **Every 5 minutes (demo)** → **Start cycle** → **Start cycle**. **Write down the time: this is Start** | **Demo club has started**, and **Round 1 of 3** | Person 2: "We agree the order together. For the demo, payouts are 5 minutes apart. Starting locks everything in and registers the cycle on the smart contract." |
| 3.4 | Wait 30 seconds. Then A, B and C each, one at a time: **Pay now** → **Confirm payment** | **Confirming…**, then **Paid** and a **Proof of payment** link | "Each member pays in rand. The platform sends the matching digital dollars to the smart contract, and only marks it Paid once the blockchain confirms it." |
| 3.5 | **All three refresh.** In window B, also open a **second tab** with the same page (right-click the tab → **Duplicate**) | Every window shows **Pay now** for round 2, including the second tab | (Nothing to say; this sets up the next step) |
| 3.6 | **The duplicate.** Window B, **first tab**: **Pay now** → **Confirm payment** → wait for **Paid**. Then the **second tab** (**do not refresh it**): **Pay now** → **Confirm payment** | The alert **Already paid**: "You've already paid for this round." | "What if someone pays twice? The platform refuses a second payment for the same round, and the smart contract would too. Nothing was taken twice." |
| 3.7 | **Only now**: A, then C: refresh, **Pay now** → **Confirm payment** | **Paid** in both | "Round 1 is fully paid, but its payout waits until round 2 is fully paid too. That stops someone collecting the money and then not paying again." Then: "Over to the admin." |

**Why 3.6 must come before 3.7:** **Pay now** always pays the first round that not everyone has paid yet. Once all three have paid round 2, the second tab's **Pay now** would pay round 3 instead of being refused.

## Person 5, part 1: the admin can't release early

Window D. **Must be done before 5 min after Start.**

| # | Do | You'll see | Say |
|---|---|---|---|
| 5.1 | **Stokvels → Rounds** (refresh). Find **Demo club**, **Round 1 of 3** | **Paid 3 of 3**, the note **Its payout time hasn't come yet.**, and **no Release payout button** | "Everyone has paid round 1, but its payout time hasn't come. Even an admin can't release it early: the screen doesn't offer it, the server refuses it, and the smart contract would reject it. The payout time is a hard rule." Then: "Let's watch it pay out." |

## Person 4: the payout

Window A and window E. From 5 min after Start.

| # | Do | You'll see | Say |
|---|---|---|---|
| 4.1 | Window A: refresh every 20 seconds, watching the **Round 1 of 3 payout** card | It moves **Everyone paid → Pool released → Sending to … → Delivered**. This takes 1 to 3 minutes | "At the payout time the platform tells the smart contract to release the money. Nobody has to press anything." |
| 4.2 | Point at **Reference** and **Proof of payment** | Both filled in | "The money becomes a normal RemitX transfer to the beneficiary in Zimbabwe, at RemitX's rate, with no extra fee. Then the digital dollars are destroyed, which stands for the beneficiary cashing out. This is the transfer's reference, and this links to the proof on the blockchain." |
| 4.3 | Window E: refresh, open the latest transactions | The payments, the release, and the destroy ("burn") | "Everything that moved money is on the public blockchain." Then: "Now round 3." |
| 4.4 | **Person 3**: A, B and C each refresh, then **Pay now** → **Confirm payment** | **Paid** in all three | "Round 3 is paid, so round 2 can pay out at 10 minutes, and round 3 at 15." |
| 4.5 | **The blocked round.** Window C: **Stokvels → Siyakhula** (refresh) | **Waiting for ⟨Member 3⟩**, and in **Members**, one **Paid** and one **Waiting** | "Here's what happens when someone doesn't pay. In this other stokvel, round 1's time has passed and it's fully paid, but one member hasn't paid round 2, so round 1 is locked. It's not lost: once they pay, it pays out." Then: "Over to the admin." |

**Don't point at the "Rounds" list's badges.** A round that's fully paid but still waiting says **Released** there, before the money has actually moved. Use the payout card and **x of 3 paid out** instead.

## Person 5, part 2: the admin side

Window D, from about 10 min after Start. Rounds 2 and 3 pay out in the background.

| # | Do | You'll see | Say |
|---|---|---|---|
| 5.2 | **Stokvels → Rounds** (refresh). Find **Siyakhula** | **Waiting for the next round to fill.** | "The admin sees the same rule: this round is paid, but it waits for the next round." |
| 5.3 | **Stokvels → Contract** | **Running**, the contract address, and **Treasury balance … UCTUSD** | "One smart contract holds every stokvel. The platform's wallet pays for the transactions; its key is encrypted, and only the background worker can use it." |
| 5.4 | **IAM → Audit log**. **Area**: **Stokvels** | The admin actions, each with who did it | "Every admin action on a stokvel is recorded." |
| 5.5 | **Optional, and only after the 15-minute payout is Delivered**: **Stokvels → Contract** → **Pause all stokvels** → Reason: **Demo** → confirm. Then window B: **Pay now** in Siyakhula. Then **Resume all stokvels** → **Resume** | **Stokvels paused**; the member sees "Stokvels are temporarily paused."; then **Stokvels resumed** | "An emergency stop for every stokvel. It stops activity until we resume, but it can never change the payout rules." |

## Closing (Person 4)

Window A, at about 17 min after Start.

| # | Do | You'll see | Say |
|---|---|---|---|
| 6.1 | Refresh. Point at **Payout order** and the **Cycle 1** card | **3 of 3 paid out** | "Three members, three rounds, and every member's beneficiary received one payout. The cycle is closed, and the members can choose to continue into a new one." |

## If something goes wrong

| What happened | What to do |
|---|---|
| Something breaks in steps 2.1 to 3.3 | Use the ready-made **Masakhane Savings Club** instead: its members, order and beneficiaries are already set. Go straight to **Start the cycle** (step 3.3) |
| **"This stokvel's cycle is still being set up"** | Wait 30 seconds, then **Pay now** again |
| Nothing shows **Pay now** | Refresh |
| A payout hasn't moved 2 minutes after its time | Check the worker is awake. Then Person 5: **Stokvels → Rounds** → **Release payout** on that round → **Release payout** |
| Step 5.1 is late (after 5 min) | Round 1 is now due, so the refusal can't be shown. Show Siyakhula's **Waiting for the next round to fill.** instead. If a marker wants proof the server refuses: `pytest api/tests/test_stokvel_blocked_duplicate_early.py -v` |
| **"temporarily unavailable"** when paying | The platform wallet is low. Top up, or play the backup video |
| QA or the blockchain is down | Play the backup video |

## If the markers ask

- **"Doesn't the admin finalise each round?"** "Ours releases automatically once a round is due. The admin's Release payout is only a backup, and the contract checks the same rules either way."
- **"Where does the money go?"** "To the beneficiary of the member whose turn it is, as a normal RemitX transfer. The fee was paid on top of each contribution, so the payout isn't charged again."
- **"What if someone never pays?"** "That round stays locked. Cancelling and refunding a stokvel isn't in this version."
- **"Can the beneficiary see the money?"** "Yes, on their Transfers page. It shows as 'From Unnamed', because the sender is the stokvel, not a person."

## Backup video

Record the whole second rehearsal: screen and sound, with all windows visible. Keep it outside the repo, and put the link in #272.

## Rehearsal log

Fill this in after each run. It's the evidence for closing #269 and #270.

| Date | Who | D1 (3 payouts) | D2 (blocked) | D3 (duplicate) | D4 (early) | What went wrong |
|---|---|---|---|---|---|---|
| | | | | | | |
| | | | | | | |
