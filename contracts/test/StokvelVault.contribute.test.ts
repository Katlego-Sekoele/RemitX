import { expect } from "chai"
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers"
import {
  CONTRIBUTION,
  INTERVAL,
  LERATO,
  MEMBERS,
  POOL,
  SIPHO,
  STOKVEL_ID as id,
  THANDI,
  deploy,
  memberId,
  payRound,
  schedule,
  startedFixture,
  uuidToBytes32,
} from "./helpers"

// Contributions and release (doc D5, D12; #198, DEC-1 #212, R1-02 #216).

/** Same as startedFixture, but every payout time is already in the past. */
async function duePayoutsFixture() {
  const f = await startedFixture()
  await time.increaseTo(f.sched.payouts[2])
  return f
}

describe("StokvelVault: contributions and release", () => {
  describe("contribute", () => {
    it("pulls exactly the contribution and records it", async () => {
      const { vault, token, operator } = await loadFixture(startedFixture)
      const tx = vault.connect(operator).contribute(id, 0, SIPHO)
      await expect(tx)
        .to.emit(vault, "ContributionMade")
        .withArgs(id, 1, 0, SIPHO, CONTRIBUTION)
      await expect(tx).to.changeTokenBalances(
        token,
        [operator, vault],
        [-CONTRIBUTION, CONTRIBUTION],
      )
      expect(await vault.hasPaid(id, 0, SIPHO)).to.be.true
      expect(await vault.paidCount(id, 0)).to.equal(1)
      expect(await vault.roundPool(id, 0)).to.equal(CONTRIBUTION)
    })

    it("rejects a duplicate contribution", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await op.contribute(id, 0, SIPHO)
      await expect(op.contribute(id, 0, SIPHO))
        .to.be.revertedWithCustomError(vault, "AlreadyPaid")
        .withArgs(0, SIPHO)
    })

    it("rejects an unknown member, including one from another stokvel", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const other = uuidToBytes32(crypto.randomUUID())
      const outsiderMember = memberId(77)
      const s = schedule(BigInt(await time.latest()) + 1n, 2)
      const op = vault.connect(operator)
      await op.createStokvel(other, CONTRIBUTION)
      await op.startCycle(
        other,
        [outsiderMember, memberId(78)],
        s.starts,
        s.deadlines,
        s.payouts,
      )
      for (const m of [memberId(99), outsiderMember]) {
        await expect(op.contribute(id, 0, m))
          .to.be.revertedWithCustomError(vault, "NotMember")
          .withArgs(m)
      }
    })

    it("rejects an unauthorised sender", async () => {
      const { vault, token, admin, outsider } =
        await loadFixture(startedFixture)
      await token.mint(outsider.address, CONTRIBUTION)
      await token
        .connect(outsider)
        .approve(await vault.getAddress(), CONTRIBUTION)
      for (const signer of [admin, outsider]) {
        await expect(
          vault.connect(signer).contribute(id, 0, SIPHO),
        ).to.be.revertedWithCustomError(
          vault,
          "AccessControlUnauthorizedAccount",
        )
      }
    })

    it("rejects an unknown stokvel, and one with no open cycle", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      const unknown = uuidToBytes32(crypto.randomUUID())
      await expect(op.contribute(unknown, 0, SIPHO))
        .to.be.revertedWithCustomError(vault, "UnknownStokvel")
        .withArgs(unknown)

      const noCycle = uuidToBytes32(crypto.randomUUID())
      await op.createStokvel(noCycle, CONTRIBUTION)
      await expect(op.contribute(noCycle, 0, SIPHO))
        .to.be.revertedWithCustomError(vault, "CycleNotOpen")
        .withArgs(noCycle)
    })

    it("rejects a round that is not open (rounds fill in order)", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await op.contribute(id, 0, SIPHO)
      await expect(op.contribute(id, 1, THANDI))
        .to.be.revertedWithCustomError(vault, "WrongRound")
        .withArgs(1, 0)

      await op.contribute(id, 0, THANDI)
      await op.contribute(id, 0, LERATO)
      // Round 1 is now open; rounds Sipho has not paid that are not open
      // report WrongRound.
      for (const r of [2, 3, 255]) {
        await expect(op.contribute(id, r, SIPHO))
          .to.be.revertedWithCustomError(vault, "WrongRound")
          .withArgs(r, 1)
      }
    })

    it("with every round paid but none due, there is nothing left to pay", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) await payRound(op, r)
      expect(await vault.openRound(id)).to.equal(3)
      await expect(op.contribute(id, 2, SIPHO))
        .to.be.revertedWithCustomError(vault, "AlreadyPaid")
        .withArgs(2, SIPHO)
      // No round 3 exists: nothing may be paid into it (funds would be stuck).
      for (const m of [SIPHO, THANDI, LERATO]) {
        await expect(op.contribute(id, 3, m))
          .to.be.revertedWithCustomError(vault, "WrongRound")
          .withArgs(3, 3)
      }
      expect(await vault.roundPool(id, 3)).to.equal(0)
    })

    it("a repeat payment into a round that has filled reports AlreadyPaid, not WrongRound", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await payRound(op, 0)
      expect(await vault.openRound(id)).to.equal(1)
      for (const m of [SIPHO, THANDI, LERATO]) {
        await expect(op.contribute(id, 0, m))
          .to.be.revertedWithCustomError(vault, "AlreadyPaid")
          .withArgs(0, m)
      }
    })

    it("a repeat payment into a released round reports AlreadyPaid", async () => {
      const { vault, operator } = await loadFixture(duePayoutsFixture)
      const op = vault.connect(operator)
      await payRound(op, 0)
      await payRound(op, 1) // releases round 0
      expect((await vault.getCycle(id, 1)).nextToFinalise).to.equal(1)
      await expect(op.contribute(id, 0, SIPHO))
        .to.be.revertedWithCustomError(vault, "AlreadyPaid")
        .withArgs(0, SIPHO)
    })

    it("rejects a short transfer (WrongAmount) and leaves no state", async () => {
      const f = await deploy("FeeOnTransferToken")
      const s = schedule(BigInt(await time.latest()) + 1n, 3)
      const op = f.vault.connect(f.operator)
      await op.createStokvel(id, CONTRIBUTION)
      await op.startCycle(id, MEMBERS, s.starts, s.deadlines, s.payouts)
      await expect(op.contribute(id, 0, SIPHO))
        .to.be.revertedWithCustomError(f.vault, "WrongAmount")
        .withArgs(CONTRIBUTION, CONTRIBUTION - CONTRIBUTION / 100n)
      expect(await f.vault.hasPaid(id, 0, SIPHO)).to.be.false
      expect(await f.vault.roundPool(id, 0)).to.equal(0)
    })

    it("rejects when the Treasury Wallet has not approved enough", async () => {
      const { vault, token, operator } = await loadFixture(startedFixture)
      await token
        .connect(operator)
        .approve(await vault.getAddress(), CONTRIBUTION - 1n)
      await expect(
        vault.connect(operator).contribute(id, 0, SIPHO),
      ).to.be.revertedWithCustomError(token, "ERC20InsufficientAllowance")
      expect(await vault.paidCount(id, 0)).to.equal(0)
    })

    it("accepts a late contribution (the deadline is informational)", async () => {
      const { vault, operator, sched } = await loadFixture(startedFixture)
      await time.increaseTo(sched.deadlines[0] + 3600n)
      await expect(
        vault.connect(operator).contribute(id, 0, SIPHO),
      ).to.emit(vault, "ContributionMade")
    })
  })

  describe("release rule: fully paid AND payout time passed (D5, D12)", () => {
    it("finalise is rejected before the payout time, even when all have paid", async () => {
      const { vault, operator, sched } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await payRound(op, 0)
      // Round 1 full too: only the payout time is missing.
      await expect(payRound(op, 1)).to.not.emit(vault, "RoundFinalised")
      expect(BigInt(await time.latest())).to.be.lessThan(sched.payouts[0])

      expect(await vault.isFinalisable(id, 0)).to.be.false
      await expect(op.finalise(id, 0))
        .to.be.revertedWithCustomError(vault, "NotYetFinalisable")
        .withArgs(0)
    })

    it("finalise succeeds once the payout time passes", async () => {
      const { vault, token, operator, releaseTarget, sched } =
        await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await payRound(op, 0)
      await payRound(op, 1)

      await time.increaseTo(sched.payouts[0] - 1n)
      expect(await vault.isFinalisable(id, 0)).to.be.false
      await time.increaseTo(sched.payouts[0])
      expect(await vault.isFinalisable(id, 0)).to.be.true

      const tx = op.finalise(id, 0)
      await expect(tx)
        .to.emit(vault, "RoundFinalised")
        .withArgs(id, 1, 0, SIPHO, POOL)
      await expect(tx).to.changeTokenBalances(
        token,
        [vault, releaseTarget],
        [-POOL, POOL],
      )
      expect(await vault.roundPool(id, 0)).to.equal(0)
      expect((await vault.getCycle(id, 1)).nextToFinalise).to.equal(1)
    })

    it("a round blocked after its payout time stays blocked, then releases when the last member pays", async () => {
      const { vault, token, operator, releaseTarget, sched } =
        await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await payRound(op, 0)
      await op.contribute(id, 1, SIPHO)
      await op.contribute(id, 1, THANDI)

      // Payout time passes; Lerato has not paid round 1.
      await time.increaseTo(sched.payouts[0] + 10n * INTERVAL)
      expect(await vault.isFinalisable(id, 0)).to.be.false
      await expect(op.finalise(id, 0))
        .to.be.revertedWithCustomError(vault, "NotYetFinalisable")
        .withArgs(0)
      expect(await token.balanceOf(releaseTarget)).to.equal(0)

      // Her payment releases round 0 in the same transaction.
      await expect(op.contribute(id, 1, LERATO))
        .to.emit(vault, "RoundFinalised")
        .withArgs(id, 1, 0, SIPHO, POOL)
      expect(await token.balanceOf(releaseTarget)).to.equal(POOL)
    })

    it("a round one short never releases, however late", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(duePayoutsFixture)
      const op = vault.connect(operator)
      await op.contribute(id, 0, SIPHO)
      await op.contribute(id, 0, THANDI)
      await time.increase(INTERVAL * 100n)

      await expect(op.contribute(id, 1, SIPHO)).to.be.revertedWithCustomError(
        vault,
        "WrongRound",
      )
      await expect(op.finalise(id, 0)).to.be.revertedWithCustomError(
        vault,
        "NotYetFinalisable",
      )
      expect(await token.balanceOf(releaseTarget)).to.equal(0)
      expect(await vault.queryFilter(vault.filters.RoundFinalised())).to.be
        .empty
    })

    it("round N waits for round N+1 to fill, even after its payout time", async () => {
      const { vault, operator } = await loadFixture(duePayoutsFixture)
      const op = vault.connect(operator)
      await expect(payRound(op, 0)).to.not.emit(vault, "RoundFinalised")
      expect(await vault.isFinalisable(id, 0)).to.be.false
    })

    it("the last round releases once fully paid and due (no next round)", async () => {
      const { vault, operator, sched } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) await payRound(op, r)

      await time.increaseTo(sched.payouts[1])
      await op.finalise(id, 0)
      await op.finalise(id, 1)
      // Round 2 is fully paid but its payout time has not passed.
      await expect(op.finalise(id, 2))
        .to.be.revertedWithCustomError(vault, "NotYetFinalisable")
        .withArgs(2)

      await time.increaseTo(sched.payouts[2])
      await expect(op.finalise(id, 2))
        .to.emit(vault, "RoundFinalised")
        .withArgs(id, 1, 2, LERATO, POOL)
        .and.to.emit(vault, "CycleClosed")
        .withArgs(id, 1)
    })

    it("finalise only releases the next round, in order", async () => {
      const { vault, operator, sched } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) await payRound(op, r)
      await time.increaseTo(sched.payouts[2])

      await expect(op.finalise(id, 1))
        .to.be.revertedWithCustomError(vault, "NotYetFinalisable")
        .withArgs(1)
      await op.finalise(id, 0)
      await expect(op.finalise(id, 0))
        .to.be.revertedWithCustomError(vault, "AlreadyFinalised")
        .withArgs(0)
    })
  })

  describe("automatic release and closing", () => {
    it("when payouts are already due, contributions release as they complete", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(duePayoutsFixture)
      const op = vault.connect(operator)
      await payRound(op, 0)
      // Completing round 1 releases round 0.
      await expect(payRound(op, 1))
        .to.emit(vault, "RoundFinalised")
        .withArgs(id, 1, 0, SIPHO, POOL)

      await op.contribute(id, 2, SIPHO)
      await op.contribute(id, 2, THANDI)
      // The cycle's last payment releases rounds 1 and 2 and closes it.
      await expect(op.contribute(id, 2, LERATO))
        .to.emit(vault, "RoundFinalised")
        .withArgs(id, 1, 1, THANDI, POOL)
        .and.to.emit(vault, "RoundFinalised")
        .withArgs(id, 1, 2, LERATO, POOL)
        .and.to.emit(vault, "CycleClosed")
        .withArgs(id, 1)

      expect(await token.balanceOf(releaseTarget)).to.equal(3n * POOL)
      expect(await token.balanceOf(await vault.getAddress())).to.equal(0)
      const c = await vault.getCycle(id, 1)
      expect(c.closed).to.be.true
      expect(c.nextToFinalise).to.equal(3)
    })

    it("each round is released exactly once, to the right member", async () => {
      const { vault, operator } = await loadFixture(duePayoutsFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) await payRound(op, r)
      const events = await vault.queryFilter(vault.filters.RoundFinalised(id))
      expect(
        events.map((e) => [Number(e.args.round), e.args.memberId]),
      ).to.deep.equal([
        [0, SIPHO],
        [1, THANDI],
        [2, LERATO],
      ])
      expect(
        await vault.queryFilter(vault.filters.CycleClosed(id)),
      ).to.have.length(1)
    })

    it("after closing, contribute and finalise are rejected", async () => {
      const { vault, operator } = await loadFixture(duePayoutsFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) await payRound(op, r)

      await expect(op.contribute(id, 0, SIPHO))
        .to.be.revertedWithCustomError(vault, "CycleNotOpen")
        .withArgs(id)
      await expect(op.finalise(id, 2))
        .to.be.revertedWithCustomError(vault, "AlreadyFinalised")
        .withArgs(2)
      await expect(op.finalise(id, 3))
        .to.be.revertedWithCustomError(vault, "CycleNotOpen")
        .withArgs(id)
      expect(await vault.isFinalisable(id, 2)).to.be.false
    })

    it("finalise rejects an unknown stokvel, no cycle, and other callers", async () => {
      const { vault, operator, outsider, admin } =
        await loadFixture(startedFixture)
      const op = vault.connect(operator)
      const unknown = uuidToBytes32(crypto.randomUUID())
      await expect(op.finalise(unknown, 0))
        .to.be.revertedWithCustomError(vault, "UnknownStokvel")
        .withArgs(unknown)
      const noCycle = uuidToBytes32(crypto.randomUUID())
      await op.createStokvel(noCycle, CONTRIBUTION)
      await expect(op.finalise(noCycle, 0))
        .to.be.revertedWithCustomError(vault, "CycleNotOpen")
        .withArgs(noCycle)
      for (const signer of [admin, outsider]) {
        await expect(
          vault.connect(signer).finalise(id, 0),
        ).to.be.revertedWithCustomError(
          vault,
          "AccessControlUnauthorizedAccount",
        )
      }
    })

    it("a second cycle runs independently of the first", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(duePayoutsFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) await payRound(op, r)

      const s2 = schedule(BigInt(await time.latest()) + 1n, 3)
      await op.startCycle(id, MEMBERS, s2.starts, s2.deadlines, s2.payouts)
      // Same members, fresh paid flags.
      expect(await vault.hasPaid(id, 0, SIPHO)).to.be.false
      await time.increaseTo(s2.payouts[2])
      for (const r of [0, 1, 2]) await payRound(op, r)
      expect(await token.balanceOf(releaseTarget)).to.equal(6n * POOL)
      expect((await vault.getCycle(id, 2)).closed).to.be.true
    })

    it("a full 12-member cycle (144 contributions) keeps the books balanced", async () => {
      const f = await deploy("MockUCTUSD", 12)
      const twelve = Array.from({ length: 12 }, (_, i) => memberId(i + 1))
      const s = schedule(BigInt(await time.latest()) + 1n, 12, 60n)
      const op = f.vault.connect(f.operator)
      await op.createStokvel(id, CONTRIBUTION)
      await op.startCycle(id, twelve, s.starts, s.deadlines, s.payouts)
      await time.increaseTo(s.payouts[11])
      const vaultAddr = await f.vault.getAddress()

      let maxGas = 0n
      for (let r = 0; r < 12; r++) {
        for (const m of twelve) {
          const receipt = await (await op.contribute(id, r, m)).wait()
          if (receipt!.gasUsed > maxGas) maxGas = receipt!.gasUsed
        }
        let held = 0n
        for (let k = 0; k < 12; k++) held += await f.vault.roundPool(id, k)
        expect(await f.token.balanceOf(vaultAddr)).to.equal(held)
      }
      expect((await f.vault.getCycle(id, 1)).closed).to.be.true
      expect(await f.token.balanceOf(f.releaseTarget)).to.equal(
        144n * CONTRIBUTION,
      )
      expect(maxGas).to.be.lessThan(300_000n)
    })
  })

  describe("reentrancy", () => {
    async function armedFixture() {
      const f = await deploy("ReentrantToken")
      const s = schedule(BigInt(await time.latest()) + 1n, 3)
      const op = f.vault.connect(f.operator)
      await op.createStokvel(id, CONTRIBUTION)
      await op.startCycle(id, MEMBERS, s.starts, s.deadlines, s.payouts)
      await time.increaseTo(s.payouts[2])
      // The token gets the operator role so its reentrant call passes
      // access control and reaches the reentrancy guard.
      await f.vault
        .connect(f.admin)
        .grantRole(await f.vault.OPERATOR_ROLE(), await f.token.getAddress())
      return f
    }

    it("a token that re-enters during an automatic release is blocked", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(armedFixture)
      const op = vault.connect(operator)
      await payRound(op, 0)
      await op.contribute(id, 1, SIPHO)
      await op.contribute(id, 1, THANDI)

      await token.arm(
        await vault.getAddress(),
        releaseTarget.address,
        vault.interface.encodeFunctionData("finalise", [id, 0]),
      )
      await expect(
        op.contribute(id, 1, LERATO),
      ).to.be.revertedWithCustomError(vault, "ReentrancyGuardReentrantCall")
      expect((await vault.getCycle(id, 1)).nextToFinalise).to.equal(0)
      expect(await vault.roundPool(id, 0)).to.equal(POOL)
      expect(await token.balanceOf(releaseTarget)).to.equal(0)
    })

    it("a token that re-enters during finalise is blocked", async () => {
      // Not-yet-due schedule, so paying does not release automatically.
      const f = await deploy("ReentrantToken")
      const s = schedule(BigInt(await time.latest()) + 1n, 3)
      const op = f.vault.connect(f.operator)
      await op.createStokvel(id, CONTRIBUTION)
      await op.startCycle(id, MEMBERS, s.starts, s.deadlines, s.payouts)
      await f.vault
        .connect(f.admin)
        .grantRole(await f.vault.OPERATOR_ROLE(), await f.token.getAddress())
      await payRound(op, 0)
      await payRound(op, 1)
      await time.increaseTo(s.payouts[0])

      await f.token.arm(
        await f.vault.getAddress(),
        f.releaseTarget.address,
        f.vault.interface.encodeFunctionData("finalise", [id, 0]),
      )
      await expect(op.finalise(id, 0)).to.be.revertedWithCustomError(
        f.vault,
        "ReentrancyGuardReentrantCall",
      )
      expect((await f.vault.getCycle(id, 1)).nextToFinalise).to.equal(0)
      expect(await f.token.balanceOf(f.releaseTarget)).to.equal(0)
    })

    it("a token that re-enters while a contribution is pulled is blocked", async () => {
      const { vault, token, operator } = await loadFixture(armedFixture)
      await token.arm(
        await vault.getAddress(),
        await vault.getAddress(),
        vault.interface.encodeFunctionData("contribute", [id, 0, THANDI]),
      )
      await expect(
        vault.connect(operator).contribute(id, 0, SIPHO),
      ).to.be.revertedWithCustomError(vault, "ReentrancyGuardReentrantCall")
      expect(await vault.paidCount(id, 0)).to.equal(0)
    })
  })
})

