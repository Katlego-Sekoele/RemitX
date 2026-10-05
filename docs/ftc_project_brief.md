# ECO5037W 2026 Class Project Brief

## 1. Background

Stokvels are rotating savings and credit associations (ROSCAs) in which a group of members contribute a fixed amount at regular intervals, and the pooled funds are paid out to one member each round, in an agreed order, until every member has received a payout. They are among the most widely used informal financial arrangements in South Africa. Stokvels give members access to a lump sum without borrowing, use social trust to enforce saving, and serve households that formal financial institutions often underserve. They also have known weaknesses: records are usually kept by hand or in messaging groups, cash handling creates a risk of loss or theft, the group depends on the honesty of whoever holds the funds, and a member who stops contributing can leave others without their expected payout.

Many stokvel members are migrant workers or have family in neighbouring countries, and a payout is often sent across a border soon after it is received. That second step usually goes through a separate remittance channel with its own fees, delays and exchange-rate costs. This project combines the two activities. A smart contract holds the contributions, records who has paid, and releases each round's pool only when the agreed rules are met. The existing FSE remittance platform then delivers the payout directly to the member's nominated beneficiary in another country. This makes the savings rules transparent and verifiable while reusing the custody, compliance and settlement infrastructure already built for FSE. It also raises questions you will need to address. These include how a stokvel is treated under South African law, where its exemption from banking regulation ends, and what obligations arise when a pooled payout is converted and sent abroad.

## 2. What you are building

You will build a rotating stokvel on top of an FSE remittance platform. Three members each contribute a fixed amount of UCTUSD every round to a smart contract on the XRPL EVM Testnet. When everyone has paid and the payout time has passed, the contract releases the pool, and FSE pays it to the scheduled member's beneficiary in another country. After three rounds, each member has had one payout and the cycle closes.

The core user journey is:

1. An administrator sets up the stokvel: three members, the contribution amount, the payout schedule and the payout order.
2. Each member logs in to the FSE platform and nominates a cross-border beneficiary.
3. In each round, each member makes their contribution. The backend sends the UCTUSD to the smart contract and records the contribution once it is confirmed on chain.
4. When all members have paid and the payout time has passed, the administrator finalises the round. The contract releases the pool to the platform settlement wallet.
5. The platform creates an FSE remittance to the scheduled member's beneficiary, using FSE's quotation and fee rules.
6. The UCTUSD is burnt to represent the beneficiary's simulated cash-out. The member can see the payout status, transaction hashes and remittance reference.
7. After three rounds, every member has received one payout and the cycle closes.

The final demo must show:

- The full journey for three synthetic members across three rounds.
- A round blocked because one member has not paid.
- A duplicate contribution and an early finalisation being rejected.

Use synthetic data, test tokens and simulated fiat payments only. Do not use real funds, real RLUSD, or production credentials.

### Mock Bank API

We have included a deployed mock bank, called *TrustMeBank*, which simulates the kind of interaction you might have with an Open Banking API in the real world.

The mock bank provides fake customers, bank accounts, balances and transaction histories. It also supports OAuth2-based account linking and customer-authorised payments.

You **may** use this API to implement more realistic ZAR deposit and withdrawal flows in your application.

For example, instead of simply increasing a user's balance when they "deposit" money, your application can:

1. Redirect the user to *TrustMeBank*.
2. Have the user authenticate and authorise a payment.
3. Receive confirmation that the payment was completed.
4. Credit the user's balance in your application.

Similarly, your application could register its own mock bank account and use it as the source or destination for fiat movements where appropriate.

The API is intentionally lightweight and simple to integrate with. It is included as an **optional extension**, not as a requirement. If your team is comfortable using it, it can make your application feel significantly more realistic by giving your fiat flows an actual source and destination rather than having balances appear or disappear without explanation.

The simplest useful integration is the **payment authorisation flow**. In this case, a user is redirected to TrustMeBank, authenticates, approves a payment to your platform, and is then returned to your application once the payment has been authorised and processed.

The API also supports access to bank account information and transaction history, so teams may use this for additional functionality where relevant.

Documentation and source code are available here:

<https://github.com/marclevin/TrustMeBank>

Deployed version:

<https://trustmebank.34-35-51-235.sslip.io/>

API documentation:

<https://trustmebank.34-35-51-235.sslip.io/docs>

## 3. How the class is organised

The whole class works as one group, extending one of the FSE platforms built in ECO5040W. You choose which groups' FSE code to work from.

The class is divided into two teams, with a management team elected from them:

- **Business team:** writes the business proposal.
- **Dev team** builds the contract, the backend integration and the web pages, with one named owner for each. Two or three team members are responsible for testing and the demo.
- **Management team:** a CEO (co-ordinates business proposal and presentation) and CTO (responsible for POC and technical decisions).

Use one shared GitHub repository, with pull requests and a project board.

## 4. Deliverables

1. Business proposal (business team), of 10 to 15 pages, covering:
   1. Problem and market: what stokvels are and their weaknesses, the cost of sending money from South Africa to neighbouring countries, how many people belong to stokvels and send money across borders, and who already serves them.
   2. Business model: who pays, sources of revenue (fees, foreign-exchange margin, interest on pooled funds), and the unit economics of one full stokvel cycle.
   3. Regulatory and risk analysis: the stokvel exemption from the Banks Act, whether holding pooled contributions counts as taking deposits, FICA and KYC, exchange control on individuals' cross-border transfers, the FSCA's crypto asset regime, safeguarding of pooled funds, and consumer protection if a member stops paying or the platform fails.
   4. Go-to-market: how existing stokvel groups are brought onto the platform, and which partners (banks, telcos, remittance agents, stokvel associations, community organisations) the model depends on.
2. Proof of concept (dev team): GitHub repository, deployed version and test suite, meeting section 7.
3. Lessons learnt document (individual, every student).
4. 10-minute presentation and 5-minute live demo.

## 5. Assessment

The project is worth 25 marks. Each student scores their own contribution out of 5 and scores each classmate out of 5. Your peer evaluation mark is the average of the scores your classmates give you.

| Component | Marks |
| --- | --- |
| Self-evaluation of your contribution | 5 |
| Peer evaluation (the average of the scores your classmates give you) | 5 |
| Final presentation and live demo | 5 |
| Proof of concept, documentation and report | 10 |
| **Total** | **25** |

## 6. Timeline

The project runs for four full weeks plus the Monday and Tuesday of week 5. Submission is on the Wednesday morning of week 5, followed by the presentation and demo that day.

### 28 September – 2 October: decisions and set-up

- Choose which groups base FSE codebase you will work from, elect the CEO and CTO, and name an owner for the contract, backend, frontend, and testing and demo.
- **Dev team:** set up the shared repository and local environments, get test XRP from the faucet, and send the platform wallet address to Marc. By Friday, agree on the contract design: its functions, events and states, and the settlement statuses in the database.
- **Business team:** divide the four proposal sections between members, agree on an outline and start collecting sources, especially for the regulatory analysis.

### 5 October – 9 October: contract and connection

- **Dev team:** build the contract and its tests and deploy it to the testnet by Friday. The backend stores the EVM key in FSE's encrypted key storage, connects with web3.py, and can submit a contribution and read the contract's state.
- **Business team:** draft the problem and market section and the regulatory analysis.
- **Friday check-in:** the contract is deployed and tested on the testnet. If this has slipped, reduce scope now rather than in week 4.

### 12 October to 16 October: one round end-to-end

- **Dev team:** get one full round working: contributions, finalisation, the FSE remittance record, the burn, and the hashes and remittance reference stored together. Build the member and admin screens.
- **Business team:** draft the business model and go-to-market sections, with a full proposal draft by Friday. The CTO checks it for consistency with the build, for example, that the fee model matches FSE's fee rules.

### 19 October to 23 October: full cycle and code freeze

- **Dev team:** run all three rounds on the deployed version, plus the blocked round and the rejected duplicate and early finalisation. The settlement retry test must pass. Freeze the code on Friday and tag the release.
- **Testing and demo:** write the demo script and prepare the synthetic data.
- **Business team:** finalise the proposal and draft the presentation slides.

### 26 October to 28 October: rehearsal and submission

- **Monday:** full demo rehearsal on the deployed version, fixing only bugs that break the demo. Record a backup video of the complete demo in case the testnet or deployment fails on the day. Every student writes their lessons learnt document.
- **Tuesday:** final rehearsal with the slides and assemble the submission.
- **Wednesday morning:** submit the tagged repository link, the deployed URL, the business proposal and the lessons learnt documents. Submit your self-evaluation and peer evaluations.
- **Wednesday:** presentation and live demo.

## 7. Technical specification

This section is mainly for the dev team. Keep the FSE application's backend, database, API, message queue, login, custodial wallets and key storage. Add a Solidity contract on the XRPL EVM Testnet (built with Hardhat or Foundry) and connect it to the backend with web3.py. Members do not connect an external wallet.

### 7.1 Smart contract

- Configure one stokvel: three member identifiers, a fixed contribution, a payout time per round and a payout order.
- Accept UCTUSD contributions submitted by the platform backend on a member's behalf, recorded against member and round.
- Reject incorrect amounts, duplicates, unknown members and unauthorised senders.
- Finalise a round only when all members have paid and the payout time has passed: transfer the pool to the settlement wallet, record the entitled member and advance the round. A round cannot be finalised twice.
- Emit contribution and payout events, and close the cycle after round three.
- Let an administrator pause and resume the contract without bypassing payout conditions.
- Use OpenZeppelin for token handling, access control, pausing and reentrancy protection.

### 7.2 Contributions and settlement

- The platform wallet holds the UCTUSD. A member's contribution is a record in the database, and the backend sends the tokens to the contract from the platform wallet. Mark a contribution as paid only after on-chain confirmation. Test XRP pays gas.
- The FSE remittance uses FSE's quotation and fee rules without charging the member again. No RLUSD moves on the XRP Ledger; this step produces the quotation, remittance record and reference.
- The settlement wallet burns the UCTUSD. Store the burn hash, beneficiary credit and remittance reference together.
- Track pool release and remittance as separate statuses. Retrying a failed settlement must not repeat the release, burn or beneficiary credit.

### 7.3 Web application

- **Member screen:** the group, contribution amount, schedule and payout order; paid and outstanding contributions; the current round and payout status; transaction hashes and remittance references.
- **Admin screen:** set up the group (a script is acceptable), finalise eligible rounds, and pause or resume the contract.
- **Beneficiaries:** reuse FSE's existing beneficiary screen for nominations.

### 7.4 Security and data

- Store EVM private keys in FSE's encrypted key storage, decryptable only by the signing component. Keys must never appear in the frontend, API, logs or source control.
- Keep personal and beneficiary data off-chain; the contract stores member identifiers only.
- Protect admin functions and validate API inputs.
- Document that the contract relies on the backend to identify the contributing member.

### 7.5 Testing

- **Contract tests:** valid contributions and payouts, incorrect amounts, duplicates, unauthorised senders, early or underfunded finalisation, repeated finalisation, pause, and closure after round three.
- **Settlement tests:** a retried settlement does not duplicate the remittance, burn or credit.
- **Demo timing:** use intervals of a few minutes between rounds.

## 8. Resources and token details

- **XRPL EVM deployment guide:** deploying Solidity contracts to the testnet.
- **XRPL EVM contract interaction:** network configuration, submitting transactions and reading contract state.
- **OpenZeppelin Contracts:** reusable token interfaces, access controls and security components.
- **web3.py:** interacting with the EVM contracts from the existing Python backend. ethers.js is an alternative for JavaScript integration.
- **XRPL EVM faucet:** obtaining test XRP for gas. Select Testnet. This faucet supplies XRP, not UCTUSD.

### UCTUSD on the XRPL EVM Testnet

| Setting | Value |
| --- | --- |
| Network | XRPL EVM Testnet |
| RPC URL | https://rpc.testnet.xrplevm.org |
| Chain ID | 1449000 |
| Token Contract | 0x7055071C7B79A859d9514e62833BFf041ce71074 |
| Decimals | 18 |
| Distributor | 0xE054D006c45586251872a7EA17Af40b907745293 |
| Explorer | UCTUSD Explorer |

To receive UCTUSD, send your platform wallet address on the XRPL EVM Testnet to Marc (LVNMAR013@myuct.ac.za). The sidechain does not use trust lines, so no setup is needed beyond a wallet address.

## 9. Out of scope

Recovering missed contributions, penalties and refunds; bridges; external wallets; credit scoring; multiple stokvels; automated scheduling; and real funds or settlement.

## Support

We will offer two weekly check-ins. One with Marc for the tech team and another with Allan for the business team. Both will happen at 11:00 on Fridays.
