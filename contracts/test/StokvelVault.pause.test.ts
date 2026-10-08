import { expect } from "chai"
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers"
import {
  CONTRIBUTION,
  LERATO,
  MEMBERS,
  POOL,
  SIPHO,
  STOKVEL_ID as id,
  THANDI,
  payRound,
  schedule,
  startedFixture,
  uuidToBytes32,
} from "./helpers"

// Pause and resume (#199 / R1-03 #217).

/** Round 0 full, round 1 one short (Lerato); payout times already due. */
async function oneShortFixture() {
  const f = await startedFixture()
  await time.increaseTo(f.sched.payouts[2])
  const op = f.vault.connect(f.operator)
  await payRound(op, 0)
  await op.contribute(id, 1, SIPHO)
  await op.contribute(id, 1, THANDI)
  return f
}

/** Rounds 0 and 1 full but not yet due; round 0 can be finalised later. */
async function readyToFinaliseFixture() {
  const f = await startedFixture()
  const op = f.vault.connect(f.operator)
  await payRound(op, 0)
  await payRound(op, 1)
  return f
}

async function snapshot(f: Awaited<ReturnType<typeof startedFixture>>) {
  const c = await f.vault.getCycle(id, 1)
  return {
    nextToFinalise: c.nextToFinalise,
    closed: c.closed,
    paid0: await f.vault.paidCount(id, 0),
    paid1: await f.vault.paidCount(id, 1),
    pool0: await f.vault.roundPool(id, 0),
    pool1: await f.vault.roundPool(id, 1),
    vaultBalance: await f.token.balanceOf(await f.vault.getAddress()),
    released: await f.token.balanceOf(f.releaseTarget.address),
  }
}

describe("StokvelVault: pause and resume", () => {
  describe("who can pause", () => {
    it("the admin can pause and resume; events name who did it", async () => {
      const { vault, admin } = await loadFixture(startedFixture)
      await expect(vault.connect(admin).pause())
        .to.emit(vault, "Paused")
        .withArgs(admin.address)
      expect(await vault.paused()).to.be.true
      await expect(vault.connect(admin).unpause())
        .to.emit(vault, "Unpaused")
        .withArgs(admin.address)
      expect(await vault.paused()).to.be.false
    })

    it("the operator and ordinary accounts cannot pause or resume", async () => {
      const { vault, admin, operator, outsider } =
        await loadFixture(startedFixture)
      for (const signer of [operator, outsider]) {
        await expect(
          vault.connect(signer).pause(),
        ).to.be.revertedWithCustomError(
          vault,
          "AccessControlUnauthorizedAccount",
        )
      }
      await vault.connect(admin).pause()
      for (const signer of [operator, outsider]) {
        await expect(
          vault.connect(signer).unpause(),
        ).to.be.revertedWithCustomError(
          vault,
          "AccessControlUnauthorizedAccount",
        )
      }
      expect(await vault.paused()).to.be.true
    })

    it("pausing twice or resuming while running reverts", async () => {
      const { vault, admin } = await loadFixture(startedFixture)
      await expect(
        vault.connect(admin).unpause(),
      ).to.be.revertedWithCustomError(vault, "ExpectedPause")
      await vault.connect(admin).pause()
      await expect(vault.connect(admin).pause()).to.be.revertedWithCustomError(
        vault,
        "EnforcedPause",
      )
    })
  })

  describe("while paused", () => {
    it("runs the ticket's example: contribute and finalise revert, then resume", async () => {
      const f = await loadFixture(oneShortFixture)
      const op = f.vault.connect(f.operator)
      const before = await snapshot(f)

      await f.vault.connect(f.admin).pause()
      // Lerato's payment would complete round 1 and release round 0.
      await expect(
        op.contribute(id, 1, LERATO),
      ).to.be.revertedWithCustomError(f.vault, "EnforcedPause")
      await expect(op.finalise(id, 0)).to.be.revertedWithCustomError(
        f.vault,
        "EnforcedPause",
      )

      await f.vault.connect(f.admin).unpause()
      expect(await snapshot(f)).to.deep.equal(before)
      await expect(op.contribute(id, 1, LERATO))
        .to.emit(f.vault, "RoundFinalised")
        .withArgs(id, 1, 0, SIPHO, POOL)
    })

    it("finalise is blocked even for a round that is ready", async () => {
      const f = await loadFixture(readyToFinaliseFixture)
      await time.increaseTo(f.sched.payouts[0])
      expect(await f.vault.isFinalisable(id, 0)).to.be.true
      const before = await snapshot(f)

      await f.vault.connect(f.admin).pause()
      await expect(
        f.vault.connect(f.operator).finalise(id, 0),
      ).to.be.revertedWithCustomError(f.vault, "EnforcedPause")
      expect(await snapshot(f)).to.deep.equal(before)
    })

    it("pause is checked before anything else, even for bad input", async () => {
      const { vault, admin, operator } = await loadFixture(startedFixture)
      await vault.connect(admin).pause()
      const nope = uuidToBytes32(crypto.randomUUID())
      await expect(
        vault.connect(operator).contribute(nope, 9, nope),
      ).to.be.revertedWithCustomError(vault, "EnforcedPause")
      await expect(
        vault.connect(operator).finalise(nope, 9),
      ).to.be.revertedWithCustomError(vault, "EnforcedPause")
    })

    it("views keep working so the backend can show state", async () => {
      const { vault, admin } = await loadFixture(oneShortFixture)
      await vault.connect(admin).pause()
      expect(await vault.paused()).to.be.true
      expect((await vault.getStokvel(id)).cycleOpen).to.be.true
      expect(await vault.openRound(id)).to.equal(1)
      expect(await vault.hasPaid(id, 1, LERATO)).to.be.false
      // isFinalisable ignores pause: it reports the release conditions.
      expect(await vault.isFinalisable(id, 0)).to.be.false
    })

    it("creating stokvels and starting cycles still work (no tokens move)", async () => {
      const { vault, admin, operator } = await loadFixture(startedFixture)
      await vault.connect(admin).pause()
      const later = uuidToBytes32(crypto.randomUUID())
      const s = schedule(BigInt(await time.latest()) + 3600n, 3)
      await vault.connect(operator).createStokvel(later, CONTRIBUTION)
      await vault
        .connect(operator)
        .startCycle(later, MEMBERS, s.starts, s.deadlines, s.payouts)
      expect((await vault.getStokvel(later)).cycleOpen).to.be.true
    })
  })

  describe("after resuming", () => {
    it("release conditions are unchanged: no early release", async () => {
      const f = await loadFixture(readyToFinaliseFixture)
      const op = f.vault.connect(f.operator)
      await f.vault.connect(f.admin).pause()
      await f.vault.connect(f.admin).unpause()

      // Payout time still not passed: still rejected.
      await expect(op.finalise(id, 0))
        .to.be.revertedWithCustomError(f.vault, "NotYetFinalisable")
        .withArgs(0)
      await expect(op.contribute(id, 1, SIPHO)).to.be.revertedWithCustomError(
        f.vault,
        "WrongRound",
      )
      expect(await f.token.balanceOf(f.releaseTarget.address)).to.equal(0)
    })

    it("a round one short stays one short across a long pause", async () => {
      const f = await loadFixture(oneShortFixture)
      await f.vault.connect(f.admin).pause()
      await time.increase(86_400n)
      await f.vault.connect(f.admin).unpause()
      expect(await f.vault.paidCount(id, 1)).to.equal(2)
      expect((await f.vault.getCycle(id, 1)).nextToFinalise).to.equal(0)
      expect(await f.vault.isFinalisable(id, 0)).to.be.false
    })

    it("a full cycle completes across several pauses", async () => {
      const { vault, token, admin, operator, releaseTarget, sched } =
        await loadFixture(startedFixture)
      await time.increaseTo(sched.payouts[2])
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) {
        for (const m of MEMBERS) {
          await vault.connect(admin).pause()
          await vault.connect(admin).unpause()
          await op.contribute(id, r, m)
        }
      }
      expect((await vault.getCycle(id, 1)).closed).to.be.true
      expect(await token.balanceOf(releaseTarget.address)).to.equal(3n * POOL)
    })
  })
})
