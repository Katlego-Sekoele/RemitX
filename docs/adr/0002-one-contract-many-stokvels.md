# One contract holds every stokvel

RemitX lets users create many stokvels, each running repeated cycles. All of
them live in a single deployed contract (`contracts/src/StokvelVault.sol`),
keyed by stokvel ID, rather than one contract per stokvel. Creating a stokvel
is a function call (`createStokvel`), not a deployment. The backend
configures one address (`STOKVEL_CONTRACT_ADDRESS`), loads one ABI, and reads
one event stream filtered by the indexed stokvel ID. This is decision D4 in
`docs/stokvel_integration.md`.

## Considered options

- **One contract per stokvel (factory pattern).** Isolates each group's funds
  and state, so a bug or a stuck stokvel cannot touch another. But every new
  stokvel costs a deployment (gas, a wait for confirmation, a new address to
  store and watch), the backend must track many addresses and event sources,
  and a fix means redeploying or migrating every stokvel.
- **One contract per cycle.** Same costs as above, multiplied by cycles.
- **One shared contract (chosen).** One deployment, one address, one ABI and
  one event stream. Per-stokvel state is a mapping entry, so adding a stokvel
  is cheap and instant.

## Consequences

- Funds of all stokvels sit in one contract. Isolation is by accounting: each
  round has its own pool (`roundPool[id][cycle][round]`), and the contract's
  token balance always equals the sum of unreleased pools (tested on a full
  12-member cycle).
- A bug or an emergency affects every stokvel at once, so the emergency stop
  is contract-wide: the Administrator's `pause` halts all token movement for
  every stokvel and never changes release conditions.
- Loops are bounded: a cycle has at most `maxMembers` members (set at
  deployment, 3 for the prototype), so gas per call stays predictable.
- The contract cannot be upgraded. A change to the rules means deploying a new
  contract and moving the backend to the new address; stokvels in progress on
  the old one finish there.
- Event consumers must filter by stokvel ID and cycle; both are in every
  event that needs them.
