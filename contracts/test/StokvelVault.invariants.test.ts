import { expect } from "chai"
import { ethers } from "hardhat"
import { time } from "@nomicfoundation/hardhat-network-helpers"
import {
  CONTRIBUTION,
  STOKVEL_ID as id,
  deploy,
  memberId,
  schedule,
} from "./helpers"

// Randomised invariant testing (#216). Hand-written tests only cover the
// cases someone thinks of; two bugs slipped past them (a duplicate reporting
// WrongRound, and a payment into a round that does not exist). Here random
// sequences of contributions (right and wrong rounds, members, duplicates),
// finalise calls, time jumps, pauses and new cycles run against a small
// reference model of the rules (doc section 1, D5, D12). After every step
// the contract must match the model, and these must always hold:
//   - the vault holds exactly the sum of the unreleased pools;
//   - nothing is ever paid into a round that does not exist;
//   - each round is released at most once, to members[round], only when
//     it and the next round are fully paid and its payout time has passed.

const SEEDS = 40
const STEPS = 60
const OUTSIDER = memberId(999)

/** Small deterministic PRNG so a failing seed can be replayed. */
function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

type Model = {
  members: string[]
  payouts: bigint[]
  paid: Set<string>[] // per round
  pool: bigint[]
  next: number // next round to release
  closed: boolean
  cycle: number
  released: bigint
  paused: boolean
}

function newCycle(m: Model, members: string[], payouts: bigint[]) {
  m.members = members
  m.payouts = payouts
  m.paid = members.map(() => new Set())
  m.pool = members.map(() => 0n)
  m.next = 0
  m.closed = false
  m.cycle += 1
}

const n = (m: Model) => m.members.length
const full = (m: Model, r: number) => r < n(m) && m.paid[r].size === n(m)

function openRound(m: Model) {
  let r = m.next
  while (r < n(m) && full(m, r)) r++
  return r
}

function finalisable(m: Model, r: number, now: bigint) {
  if (m.closed || r !== m.next || r >= n(m)) return false
  if (!full(m, r)) return false
  if (r + 1 < n(m) && !full(m, r + 1)) return false
  return now >= m.payouts[r]
}

function release(m: Model, r: number) {
  m.released += m.pool[r]
  m.pool[r] = 0n
  m.next = r + 1
  if (r + 1 === n(m)) m.closed = true
}

/** Expected custom error for contribute, or null for success. */
function expectContribute(m: Model, r: number, who: string): string | null {
  if (m.paused) return "EnforcedPause"
  if (m.closed) return "CycleNotOpen"
  if (!m.members.includes(who)) return "NotMember"
  if (r < n(m) && m.paid[r].has(who)) return "AlreadyPaid"
  const open = openRound(m)
  if (r !== open || open >= n(m)) return "WrongRound"
  return null
}

/** Expected custom error for finalise, or null for success. */
function expectFinalise(m: Model, r: number, now: bigint): string | null {
  if (m.paused) return "EnforcedPause"
  if (r < m.next) return "AlreadyFinalised"
  if (m.closed) return "CycleNotOpen"
  if (!finalisable(m, r, now)) return "NotYetFinalisable"
  return null
}

describe("StokvelVault: randomised invariants", function () {
  this.timeout(600_000)

  for (const members of [3, 2]) {
    it(`${SEEDS} random runs of ${STEPS} steps with ${members} members match the model`, async () => {
      for (let seed = 1; seed <= SEEDS; seed++) {
        const rand = rng(seed * 7919 + members)
        const pick = <T>(xs: T[]) => xs[Math.floor(rand() * xs.length)]
        const f = await deploy()
        const op = f.vault.connect(f.operator)
        const vaultAddr = await f.vault.getAddress()
        const ids = Array.from({ length: members }, (_, i) => memberId(seed * 10 + i))

        let now = BigInt(await time.latest())
        const step = async (by: number) => {
          now += BigInt(by)
          await time.setNextBlockTimestamp(now)
        }
        const startCycle = async (m: Model) => {
          const s = schedule(now + 2n, members, BigInt(20 + Math.floor(rand() * 200)))
          await step(1)
          await op.startCycle(id, ids, s.starts, s.deadlines, s.payouts)
          newCycle(m, ids, s.payouts)
        }

        const model: Model = {
          members: [], payouts: [], paid: [], pool: [], next: 0,
          closed: true, cycle: 0, released: 0n, paused: false,
        }
        await step(1)
        await op.createStokvel(id, CONTRIBUTION)
        await startCycle(model)

        for (let i = 0; i < STEPS; i++) {
          const where = `seed ${seed}, step ${i}`
          const roll = rand()

          if (roll < 0.55) {
            // contribute: usually the open round, sometimes anything
            const r = rand() < 0.6 ? openRound(model) : pick([0, 1, 2, 3, 4, 255])
            const who = rand() < 0.9 ? pick(ids) : OUTSIDER
            await step(1 + Math.floor(rand() * 60))
            const want = expectContribute(model, r, who)
            const tx = op.contribute(id, r, who)
            if (want) {
              await expect(tx, `${where}: contribute(${r})`).to.be.revertedWithCustomError(f.vault, want)
            } else {
              await tx
              model.paid[r].add(who)
              model.pool[r] += CONTRIBUTION
              while (finalisable(model, model.next, now)) release(model, model.next)
            }
          } else if (roll < 0.75) {
            // finalise any round, due or not
            const r = rand() < 0.6 ? model.next : pick([0, 1, 2, 3])
            await step(1 + Math.floor(rand() * 120))
            const want = expectFinalise(model, r, now)
            const tx = op.finalise(id, r)
            if (want) {
              await expect(tx, `${where}: finalise(${r})`).to.be.revertedWithCustomError(f.vault, want)
            } else {
              await tx
              release(model, r)
            }
          } else if (roll < 0.85) {
            // jump time, sometimes past every payout time
            now += BigInt(rand() < 0.3 ? 2000 : Math.floor(rand() * 300))
            await time.setNextBlockTimestamp(now)
            await ethers.provider.send("evm_mine", [])
          } else if (roll < 0.93) {
            // pause or resume
            await step(1)
            if (model.paused) await f.vault.connect(f.admin).unpause()
            else await f.vault.connect(f.admin).pause()
            model.paused = !model.paused
          } else if (model.closed) {
            await startCycle(model)
          }

          // --- the contract must match the model -------------------------
          const c = await f.vault.getCycle(id, model.cycle)
          expect(Number(c.nextToFinalise), `${where}: nextToFinalise`).to.equal(model.next)
          expect(c.closed, `${where}: closed`).to.equal(model.closed)
          let held = 0n
          for (let r = 0; r < members; r++) {
            expect(await f.vault.roundPool(id, r), `${where}: pool ${r}`).to.equal(model.pool[r])
            expect(Number(await f.vault.paidCount(id, r)), `${where}: paid ${r}`).to.equal(model.paid[r].size)
            held += model.pool[r]
          }
          // Nothing ever lands in a round that does not exist.
          for (const r of [members, members + 1, 255]) {
            expect(await f.vault.roundPool(id, r), `${where}: pool ${r}`).to.equal(0n)
          }
          // The vault holds exactly the unreleased pools of the current cycle
          // (earlier cycles are fully released when they close).
          expect(await f.token.balanceOf(vaultAddr), `${where}: vault balance`).to.equal(held)
          expect(await f.token.balanceOf(f.releaseTarget), `${where}: released`).to.equal(model.released)
          expect(await f.vault.paused(), `${where}: paused`).to.equal(model.paused)
        }

        // Every release went to the right member, once per round.
        const events = await f.vault.queryFilter(f.vault.filters.RoundFinalised(id))
        const seen = new Set<string>()
        for (const e of events) {
          const key = `${e.args.cycle}:${e.args.round}`
          expect(seen.has(key), `seed ${seed}: round ${key} released twice`).to.be.false
          seen.add(key)
          expect(e.args.memberId, `seed ${seed}: recipient of ${key}`).to.equal(ids[Number(e.args.round)])
          expect(e.args.pool, `seed ${seed}: pool of ${key}`).to.equal(CONTRIBUTION * BigInt(members))
        }
      }
    })
  }
})
