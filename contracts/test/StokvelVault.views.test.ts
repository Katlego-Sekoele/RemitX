import { expect } from "chai"
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers"
import {
  CONTRIBUTION,
  LERATO,
  MEMBERS,
  SIPHO,
  STOKVEL_ID as id,
  THANDI,
  memberId,
  payRound,
  startedFixture,
  uuidToBytes32,
} from "./helpers"

// View functions (R1-01 #215): one test per view. Views read the current
// (latest) cycle unless they take a cycle number.

const unknown = uuidToBytes32("00000000-0000-4000-8000-0000000000ff")

describe("StokvelVault: views", () => {
  it("getStokvel: contribution, current cycle and whether it is open", async () => {
    const { vault } = await loadFixture(startedFixture)
    const s = await vault.getStokvel(id)
    expect(s.contribution).to.equal(CONTRIBUTION)
    expect(s.currentCycle).to.equal(1)
    expect(s.cycleOpen).to.be.true
    await expect(vault.getStokvel(unknown))
      .to.be.revertedWithCustomError(vault, "UnknownStokvel")
      .withArgs(unknown)
  })

  it("getCycle: members, schedule and progress of any started cycle", async () => {
    const { vault, sched } = await loadFixture(startedFixture)
    const c = await vault.getCycle(id, 1)
    expect(c.members).to.deep.equal(MEMBERS)
    expect(c.roundStartTimes).to.deep.equal(sched.starts)
    expect(c.roundDeadlines).to.deep.equal(sched.deadlines)
    expect(c.payoutTimes).to.deep.equal(sched.payouts)
    expect(c.nextToFinalise).to.equal(0)
    expect(c.closed).to.be.false
    await expect(vault.getCycle(unknown, 1))
      .to.be.revertedWithCustomError(vault, "UnknownStokvel")
      .withArgs(unknown)
    for (const cycle of [0, 2]) {
      await expect(vault.getCycle(id, cycle))
        .to.be.revertedWithCustomError(vault, "UnknownCycle")
        .withArgs(cycle)
    }
  })

  it("hasPaid: per member and round", async () => {
    const { vault, operator } = await loadFixture(startedFixture)
    expect(await vault.hasPaid(id, 0, SIPHO)).to.be.false
    await vault.connect(operator).contribute(id, 0, SIPHO)
    expect(await vault.hasPaid(id, 0, SIPHO)).to.be.true
    expect(await vault.hasPaid(id, 0, THANDI)).to.be.false
    expect(await vault.hasPaid(id, 1, SIPHO)).to.be.false
    await expect(
      vault.hasPaid(unknown, 0, SIPHO),
    ).to.be.revertedWithCustomError(vault, "UnknownStokvel")
  })

  it("roundPool: grows with contributions and is 0 once released", async () => {
    const { vault, operator, sched } = await loadFixture(startedFixture)
    const op = vault.connect(operator)
    await op.contribute(id, 0, SIPHO)
    expect(await vault.roundPool(id, 0)).to.equal(CONTRIBUTION)
    await op.contribute(id, 0, THANDI)
    await op.contribute(id, 0, LERATO)
    expect(await vault.roundPool(id, 0)).to.equal(3n * CONTRIBUTION)

    await payRound(op, 1)
    await time.increaseTo(sched.payouts[0])
    await op.finalise(id, 0)
    expect(await vault.roundPool(id, 0)).to.equal(0)
    expect(await vault.roundPool(id, 1)).to.equal(3n * CONTRIBUTION)
  })

  it("isFinalisable: needs the paid condition AND the payout time", async () => {
    const { vault, operator, sched } = await loadFixture(startedFixture)
    const op = vault.connect(operator)

    // Neither condition.
    expect(await vault.isFinalisable(id, 0)).to.be.false
    // Paid condition only (rounds 0 and 1 full), before the payout time.
    await payRound(op, 0)
    await payRound(op, 1)
    expect(await vault.isFinalisable(id, 0)).to.be.false
    // Both.
    await time.increaseTo(sched.payouts[0])
    expect(await vault.isFinalisable(id, 0)).to.be.true
    // Not the next round to release.
    expect(await vault.isFinalisable(id, 1)).to.be.false
    // Released: no longer finalisable.
    await op.finalise(id, 0)
    expect(await vault.isFinalisable(id, 0)).to.be.false
    await expect(vault.isFinalisable(unknown, 0))
      .to.be.revertedWithCustomError(vault, "UnknownStokvel")
      .withArgs(unknown)
    // No cycle yet: false rather than a revert.
    const fresh = uuidToBytes32(crypto.randomUUID())
    await op.createStokvel(fresh, CONTRIBUTION)
    expect(await vault.isFinalisable(fresh, 0)).to.be.false
  })

  it("isFinalisable: time alone is not enough", async () => {
    const { vault, operator, sched } = await loadFixture(startedFixture)
    await time.increaseTo(sched.payouts[2] + 3600n)
    await payRound(vault.connect(operator), 0)
    expect(await vault.isFinalisable(id, 0)).to.be.false
  })

  it("isMember: current cycle only", async () => {
    const { vault } = await loadFixture(startedFixture)
    for (const m of MEMBERS) expect(await vault.isMember(id, m)).to.be.true
    expect(await vault.isMember(id, memberId(42))).to.be.false
  })

  it("paidCount: counts payments per round", async () => {
    const { vault, operator } = await loadFixture(startedFixture)
    const op = vault.connect(operator)
    expect(await vault.paidCount(id, 0)).to.equal(0)
    await op.contribute(id, 0, SIPHO)
    await op.contribute(id, 0, THANDI)
    expect(await vault.paidCount(id, 0)).to.equal(2)
  })

  it("openRound: moves on as rounds fill; reverts with no open cycle", async () => {
    const { vault, operator } = await loadFixture(startedFixture)
    const op = vault.connect(operator)
    expect(await vault.openRound(id)).to.equal(0)
    await payRound(op, 0)
    expect(await vault.openRound(id)).to.equal(1)

    const fresh = uuidToBytes32(crypto.randomUUID())
    await op.createStokvel(fresh, CONTRIBUTION)
    await expect(vault.openRound(fresh))
      .to.be.revertedWithCustomError(vault, "CycleNotOpen")
      .withArgs(fresh)
  })
})
