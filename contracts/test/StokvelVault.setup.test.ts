import { expect } from "chai"
import { ethers } from "hardhat"
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers"
import {
  CONTRIBUTION,
  MAX_MEMBERS,
  MEMBERS,
  STOKVEL_ID as id,
  deploy,
  memberId,
  payRound,
  schedule,
  startedFixture,
  uuidToBytes32,
} from "./helpers"

// Deployment, createStokvel and startCycle (doc section 1; DEC-1 #212,
// DEC-3 #213).

const deployFixture = () => deploy()

async function createdFixture() {
  const f = await deploy()
  await f.vault.connect(f.operator).createStokvel(id, CONTRIBUTION)
  const sched = schedule(BigInt(await time.latest()) + 60n, MEMBERS.length)
  return { ...f, sched }
}

describe("StokvelVault: setup", () => {
  describe("deployment", () => {
    it("fixes the token, release target, member cap and roles", async () => {
      const { vault, admin, operator, token, releaseTarget } =
        await loadFixture(deployFixture)
      expect(await vault.token()).to.equal(await token.getAddress())
      expect(await vault.releaseTarget()).to.equal(releaseTarget.address)
      expect(await vault.maxMembers()).to.equal(MAX_MEMBERS)
      expect(await vault.MIN_MEMBERS()).to.equal(2)
      expect(await vault.hasRole(await vault.DEFAULT_ADMIN_ROLE(), admin)).to
        .be.true
      expect(await vault.hasRole(await vault.OPERATOR_ROLE(), operator)).to.be
        .true
      expect(await vault.hasRole(await vault.OPERATOR_ROLE(), admin)).to.be
        .false
    })

    it("rejects a zero address, admin == operator, and a cap below 2", async () => {
      const [a, b, c, d] = await ethers.getSigners()
      const Vault = await ethers.getContractFactory("StokvelVault")
      const Z = ethers.ZeroAddress
      for (const args of [
        [Z, b, c, d],
        [a, Z, c, d],
        [a, b, Z, d],
        [a, b, c, Z],
      ] as const) {
        await expect(
          Vault.deploy(args[0], args[1], args[2], args[3], 3),
        ).to.be.revertedWithCustomError(Vault, "ZeroAddress")
      }
      await expect(Vault.deploy(a, a, c, d, 3)).to.be.revertedWithCustomError(
        Vault,
        "AdminIsOperator",
      )
      await expect(Vault.deploy(a, b, c, d, 1))
        .to.be.revertedWithCustomError(Vault, "InvalidMaxMembers")
        .withArgs(1)
    })
  })

  describe("uuidToBytes32", () => {
    it("packs the 16 UUID bytes left-aligned", () => {
      expect(uuidToBytes32("5f0c2a1e-8d3b-4c6a-9e71-2b4f6d8a0c13")).to.equal(
        "0x5f0c2a1e8d3b4c6a9e712b4f6d8a0c1300000000000000000000000000000000",
      )
      expect(() => uuidToBytes32("not-a-uuid")).to.throw()
    })
  })

  describe("createStokvel", () => {
    it("registers the stokvel with no cycle yet", async () => {
      const { vault, operator } = await loadFixture(deployFixture)
      await expect(vault.connect(operator).createStokvel(id, CONTRIBUTION))
        .to.emit(vault, "StokvelCreated")
        .withArgs(id, CONTRIBUTION)
      const s = await vault.getStokvel(id)
      expect(s.contribution).to.equal(CONTRIBUTION)
      expect(s.currentCycle).to.equal(0)
      expect(s.cycleOpen).to.be.false
    })

    it("only the operator can create", async () => {
      const { vault, admin, outsider } = await loadFixture(deployFixture)
      for (const signer of [admin, outsider]) {
        await expect(
          vault.connect(signer).createStokvel(id, CONTRIBUTION),
        ).to.be.revertedWithCustomError(
          vault,
          "AccessControlUnauthorizedAccount",
        )
      }
    })

    it("rejects a duplicate ID, a zero ID and a zero contribution", async () => {
      const { vault, operator } = await loadFixture(deployFixture)
      const op = vault.connect(operator)
      await op.createStokvel(id, CONTRIBUTION)
      await expect(op.createStokvel(id, CONTRIBUTION))
        .to.be.revertedWithCustomError(vault, "StokvelExists")
        .withArgs(id)
      await expect(
        op.createStokvel(ethers.ZeroHash, CONTRIBUTION),
      ).to.be.revertedWithCustomError(vault, "ZeroId")
      await expect(
        op.createStokvel(uuidToBytes32(crypto.randomUUID()), 0),
      ).to.be.revertedWithCustomError(vault, "ZeroContribution")
    })
  })

  describe("startCycle", () => {
    it("fixes members (payout order) and schedule, and opens round 0", async () => {
      const { vault, operator, sched } = await loadFixture(createdFixture)
      await expect(
        vault
          .connect(operator)
          .startCycle(id, MEMBERS, sched.starts, sched.deadlines, sched.payouts),
      )
        .to.emit(vault, "CycleStarted")
        .withArgs(id, 1)

      const s = await vault.getStokvel(id)
      expect(s.currentCycle).to.equal(1)
      expect(s.cycleOpen).to.be.true
      const c = await vault.getCycle(id, 1)
      expect(c.members).to.deep.equal(MEMBERS)
      expect(c.roundStartTimes).to.deep.equal(sched.starts)
      expect(c.roundDeadlines).to.deep.equal(sched.deadlines)
      expect(c.payoutTimes).to.deep.equal(sched.payouts)
      expect(c.nextToFinalise).to.equal(0)
      expect(c.closed).to.be.false
      expect(await vault.openRound(id)).to.equal(0)
    })

    it("only the operator can start a cycle", async () => {
      const { vault, outsider, sched } = await loadFixture(createdFixture)
      await expect(
        vault
          .connect(outsider)
          .startCycle(id, MEMBERS, sched.starts, sched.deadlines, sched.payouts),
      ).to.be.revertedWithCustomError(vault, "AccessControlUnauthorizedAccount")
    })

    it("rejects an unknown stokvel", async () => {
      const { vault, operator, sched } = await loadFixture(createdFixture)
      const unknown = uuidToBytes32(crypto.randomUUID())
      await expect(
        vault
          .connect(operator)
          .startCycle(
            unknown,
            MEMBERS,
            sched.starts,
            sched.deadlines,
            sched.payouts,
          ),
      )
        .to.be.revertedWithCustomError(vault, "UnknownStokvel")
        .withArgs(unknown)
    })

    it("member count: fewer than 2 or more than maxMembers revert", async () => {
      const { vault, operator, sched } = await loadFixture(createdFixture)
      const op = vault.connect(operator)
      const one = schedule(sched.starts[0], 1)
      await expect(
        op.startCycle(id, [MEMBERS[0]], one.starts, one.deadlines, one.payouts),
      )
        .to.be.revertedWithCustomError(vault, "TooFewMembers")
        .withArgs(1)

      const four = [...MEMBERS, memberId(4)]
      const s4 = schedule(sched.starts[0], 4)
      await expect(
        op.startCycle(id, four, s4.starts, s4.deadlines, s4.payouts),
      )
        .to.be.revertedWithCustomError(vault, "MaxMembersExceeded")
        .withArgs(4, MAX_MEMBERS)
    })

    it("exactly 2 members is accepted", async () => {
      const { vault, operator, sched } = await loadFixture(createdFixture)
      const s2 = schedule(sched.starts[0], 2)
      await vault
        .connect(operator)
        .startCycle(id, MEMBERS.slice(0, 2), s2.starts, s2.deadlines, s2.payouts)
      expect((await vault.getCycle(id, 1)).members).to.have.length(2)
    })

    it("maxMembers is a deployment setting, not a fixed 3", async () => {
      const f = await deploy("MockUCTUSD", 12)
      await f.vault.connect(f.operator).createStokvel(id, CONTRIBUTION)
      const twelve = Array.from({ length: 12 }, (_, i) => memberId(i + 1))
      const s12 = schedule(BigInt(await time.latest()) + 60n, 12)
      await f.vault
        .connect(f.operator)
        .startCycle(id, twelve, s12.starts, s12.deadlines, s12.payouts)
      expect((await f.vault.getCycle(id, 1)).members).to.have.length(12)
    })

    it("rejects a duplicate member and a zero member ID", async () => {
      const { vault, operator, sched } = await loadFixture(createdFixture)
      const op = vault.connect(operator)
      await expect(
        op.startCycle(
          id,
          [MEMBERS[0], MEMBERS[1], MEMBERS[0]],
          sched.starts,
          sched.deadlines,
          sched.payouts,
        ),
      )
        .to.be.revertedWithCustomError(vault, "DuplicateMember")
        .withArgs(MEMBERS[0])
      await expect(
        op.startCycle(
          id,
          [MEMBERS[0], ethers.ZeroHash, MEMBERS[2]],
          sched.starts,
          sched.deadlines,
          sched.payouts,
        ),
      ).to.be.revertedWithCustomError(vault, "ZeroMemberId")
    })

    it("rejects schedule arrays of the wrong length", async () => {
      const { vault, operator, sched } = await loadFixture(createdFixture)
      const op = vault.connect(operator)
      for (const [s, d, p] of [
        [sched.starts.slice(1), sched.deadlines, sched.payouts],
        [sched.starts, sched.deadlines.slice(1), sched.payouts],
        [sched.starts, sched.deadlines, [...sched.payouts, 9n]],
      ]) {
        await expect(
          op.startCycle(id, MEMBERS, s, d, p),
        ).to.be.revertedWithCustomError(vault, "ScheduleLengthMismatch")
      }
    })

    it("rejects a schedule out of order within or between rounds", async () => {
      const { vault, operator, sched } = await loadFixture(createdFixture)
      const op = vault.connect(operator)
      const bad = (
        mutate: (s: ReturnType<typeof schedule>) => void,
        round: number,
      ) => {
        const s = {
          starts: [...sched.starts],
          deadlines: [...sched.deadlines],
          payouts: [...sched.payouts],
        }
        mutate(s)
        return expect(
          op.startCycle(id, MEMBERS, s.starts, s.deadlines, s.payouts),
        )
          .to.be.revertedWithCustomError(vault, "InvalidSchedule")
          .withArgs(round)
      }
      // Deadline before start.
      await bad((s) => (s.deadlines[1] = s.starts[1] - 1n), 1)
      // Payout before deadline.
      await bad((s) => (s.payouts[0] = s.deadlines[0] - 1n), 0)
      // Round 2 starts before round 1.
      await bad((s) => {
        s.starts[2] = s.starts[1] - 1n
        s.deadlines[2] = s.starts[2]
      }, 2)
    })

    it("rejects payout times that go backwards, even when each round is valid", async () => {
      const { vault, operator } = await loadFixture(createdFixture)
      const t = BigInt(await time.latest()) + 60n
      // Each round has start <= deadline <= payout and starts move forward,
      // but round 2 pays out before round 1.
      const starts = [t, t + 10n, t + 20n]
      const deadlines = [t, t + 10n, t + 20n]
      const payouts = [t + 100n, t + 1000n, t + 500n]
      await expect(
        vault
          .connect(operator)
          .startCycle(id, MEMBERS, starts, deadlines, payouts),
      )
        .to.be.revertedWithCustomError(vault, "InvalidSchedule")
        .withArgs(2)
    })

    it("allows equal times (start = deadline = payout, and between rounds)", async () => {
      const { vault, operator } = await loadFixture(createdFixture)
      const t = BigInt(await time.latest()) + 60n
      const same = [t, t, t]
      await vault.connect(operator).startCycle(id, MEMBERS, same, same, same)
      expect((await vault.getCycle(id, 1)).payoutTimes).to.deep.equal(same)
    })

    it("cannot start a second cycle while one is open", async () => {
      const { vault, operator, sched } = await loadFixture(startedFixture)
      await expect(
        vault
          .connect(operator)
          .startCycle(id, MEMBERS, sched.starts, sched.deadlines, sched.payouts),
      )
        .to.be.revertedWithCustomError(vault, "CycleInProgress")
        .withArgs(id)
    })

    it("starts the next cycle after the last one closes, with new members", async () => {
      const { vault, operator, sched } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await time.increaseTo(sched.payouts[2])
      for (const r of [0, 1, 2]) await payRound(op, r)
      expect((await vault.getStokvel(id)).cycleOpen).to.be.false

      // Lerato leaves, Zanele joins; the Organiser reset the payout order.
      const zanele = memberId(9)
      const next = [MEMBERS[1], MEMBERS[0], zanele]
      const s2 = schedule(BigInt(await time.latest()) + 60n, 3)
      await expect(
        op.startCycle(id, next, s2.starts, s2.deadlines, s2.payouts),
      )
        .to.emit(vault, "CycleStarted")
        .withArgs(id, 2)

      expect(await vault.isMember(id, zanele)).to.be.true
      expect(await vault.isMember(id, MEMBERS[2])).to.be.false
      expect(await vault.paidCount(id, 0)).to.equal(0)
      expect(await vault.openRound(id)).to.equal(0)
      // The closed cycle stays readable.
      expect((await vault.getCycle(id, 1)).closed).to.be.true
      expect((await vault.getCycle(id, 2)).members).to.deep.equal(next)
    })

    it("a failed startCycle leaves no state behind", async () => {
      const { vault, operator, sched } = await loadFixture(createdFixture)
      const op = vault.connect(operator)
      const badPayouts = [...sched.payouts]
      badPayouts[2] = 0n
      await expect(
        op.startCycle(id, MEMBERS, sched.starts, sched.deadlines, badPayouts),
      ).to.be.revertedWithCustomError(vault, "InvalidSchedule")
      expect((await vault.getStokvel(id)).currentCycle).to.equal(0)
      // Members were not left registered: the real start still works.
      await op.startCycle(id, MEMBERS, sched.starts, sched.deadlines, sched.payouts)
      expect((await vault.getStokvel(id)).currentCycle).to.equal(1)
    })
  })

  describe("roles", () => {
    it("the admin can hand the operator role to a new Treasury Wallet", async () => {
      const { vault, admin, operator, outsider } =
        await loadFixture(deployFixture)
      const OPERATOR = await vault.OPERATOR_ROLE()
      await vault.connect(admin).grantRole(OPERATOR, outsider.address)
      await vault.connect(admin).revokeRole(OPERATOR, operator.address)
      await vault.connect(outsider).createStokvel(id, CONTRIBUTION)
      await expect(
        vault
          .connect(operator)
          .createStokvel(uuidToBytes32(crypto.randomUUID()), CONTRIBUTION),
      ).to.be.revertedWithCustomError(vault, "AccessControlUnauthorizedAccount")
    })

    it("the operator cannot grant roles", async () => {
      const { vault, operator, outsider } = await loadFixture(deployFixture)
      await expect(
        vault
          .connect(operator)
          .grantRole(await vault.OPERATOR_ROLE(), outsider.address),
      ).to.be.revertedWithCustomError(vault, "AccessControlUnauthorizedAccount")
    })
  })
})
