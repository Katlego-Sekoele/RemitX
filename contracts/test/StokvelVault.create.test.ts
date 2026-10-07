import { expect } from "chai"
import { ethers } from "hardhat"
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers"

// #197: stokvels and cycles (create, update before start, views).

const id = ethers.id("stokvel-42")
// Member IDs as the backend should derive them: HMAC(serverSecret,
// stokvelId || userId). Not reversible without the secret, and the same
// person gets a different ID in each stokvel.
const SERVER_SECRET = ethers.toUtf8Bytes("test-only-member-id-secret")
const member = (userId: string, stokvelId: string = id) =>
  ethers.computeHmac(
    "sha256",
    SERVER_SECRET,
    ethers.concat([stokvelId, ethers.toUtf8Bytes(userId)]),
  )
const members = [member("sipho"), member("thandi"), member("lerato")]
const contribution = ethers.parseUnits("500", 18)
const interval = 300n // 5 minutes between rounds for the demo

async function deployFixture() {
  const [admin, operator, outsider, token, releaseTarget] =
    await ethers.getSigners()
  const vault = await ethers.deployContract("StokvelVault", [
    admin.address,
    operator.address,
    token.address,
    releaseTarget.address,
  ])
  const startTime = BigInt(await time.latest()) + 3600n
  return { vault, admin, operator, outsider, token, releaseTarget, startTime }
}

describe("StokvelVault: stokvels and cycles", () => {
  describe("deployment", () => {
    it("fixes the token, release target and roles", async () => {
      const { vault, admin, operator, token, releaseTarget } =
        await loadFixture(deployFixture)
      expect(await vault.token()).to.equal(token.address)
      expect(await vault.releaseTarget()).to.equal(releaseTarget.address)
      expect(await vault.hasRole(await vault.DEFAULT_ADMIN_ROLE(), admin))
        .to.be.true
      expect(await vault.hasRole(await vault.OPERATOR_ROLE(), operator)).to.be
        .true
      expect(await vault.hasRole(await vault.OPERATOR_ROLE(), admin)).to.be
        .false
      expect(await vault.MIN_MEMBERS()).to.equal(2n)
      expect(await vault.MAX_MEMBERS()).to.equal(12n)
    })

    it("rejects a zero address", async () => {
      const [a, b, c] = await ethers.getSigners()
      const Vault = await ethers.getContractFactory("StokvelVault")
      await expect(
        ethers.deployContract("StokvelVault", [
          a.address,
          b.address,
          ethers.ZeroAddress,
          c.address,
        ]),
      ).to.be.revertedWithCustomError(Vault, "ZeroAddress")
    })
  })

  describe("createStokvel", () => {
    it("stores the stokvel and emits StokvelCreated", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)

      await expect(
        vault
          .connect(operator)
          .createStokvel(id, members, contribution, startTime, interval),
      )
        .to.emit(vault, "StokvelCreated")
        .withArgs(id, members, contribution, startTime, interval)

      const s = await vault.getStokvel(id)
      expect(s.members).to.deep.equal(members)
      expect(s.contribution).to.equal(contribution)
      expect(s.startTime).to.equal(startTime)
      expect(s.interval).to.equal(interval)
      expect(s.currentRound).to.equal(0n)
      expect(s.closed).to.be.false
      expect(await vault.exists(id)).to.be.true
      for (const m of members) expect(await vault.isMember(id, m)).to.be.true
      expect(await vault.isMember(id, member("nobody"))).to.be.false
    })

    it("keeps stokvels separate by ID", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      const other = ethers.id("stokvel-43")
      const otherMembers = [member("sipho", other), member("thandi", other)]
      await vault
        .connect(operator)
        .createStokvel(id, members, contribution, startTime, interval)
      await vault
        .connect(operator)
        .createStokvel(other, otherMembers, 1n, startTime, 60n)

      expect((await vault.getStokvel(id)).members).to.have.length(3)
      expect((await vault.getStokvel(other)).members).to.have.length(2)
      // Same people, unlinkable IDs: neither stokvel knows the other's.
      expect(otherMembers[0]).to.not.equal(members[0])
      expect(await vault.isMember(other, members[0])).to.be.false
      expect(await vault.isMember(id, otherMembers[0])).to.be.false
    })

    it("only the operator can create", async () => {
      const { vault, admin, outsider, startTime } =
        await loadFixture(deployFixture)
      for (const signer of [admin, outsider]) {
        await expect(
          vault
            .connect(signer)
            .createStokvel(id, members, contribution, startTime, interval),
        ).to.be.revertedWithCustomError(
          vault,
          "AccessControlUnauthorizedAccount",
        )
      }
    })

    it("reverts on a duplicate ID", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      await vault
        .connect(operator)
        .createStokvel(id, members, contribution, startTime, interval)
      await expect(
        vault
          .connect(operator)
          .createStokvel(id, members, contribution, startTime, interval),
      )
        .to.be.revertedWithCustomError(vault, "StokvelExists")
        .withArgs(id)
    })

    it("reverts on a zero ID", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      await expect(
        vault
          .connect(operator)
          .createStokvel(
            ethers.ZeroHash,
            members,
            contribution,
            startTime,
            interval,
          ),
      ).to.be.revertedWithCustomError(vault, "ZeroStokvelId")
    })

    it("reverts on a duplicate member", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      const dup = [members[0], members[1], members[0]]
      await expect(
        vault
          .connect(operator)
          .createStokvel(id, dup, contribution, startTime, interval),
      )
        .to.be.revertedWithCustomError(vault, "DuplicateMember")
        .withArgs(members[0])
    })

    it("reverts on a zero member ID", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      await expect(
        vault
          .connect(operator)
          .createStokvel(
            id,
            [members[0], ethers.ZeroHash],
            contribution,
            startTime,
            interval,
          ),
      ).to.be.revertedWithCustomError(vault, "ZeroMemberId")
    })

    it("reverts with fewer than 2 members", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      for (const list of [[], [members[0]]]) {
        await expect(
          vault
            .connect(operator)
            .createStokvel(id, list, contribution, startTime, interval),
        )
          .to.be.revertedWithCustomError(vault, "InvalidMemberCount")
          .withArgs(list.length)
      }
    })

    it("accepts 12 members and reverts with 13", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      const many = Array.from({ length: 13 }, (_, i) => member(`m${i}`))

      await expect(
        vault
          .connect(operator)
          .createStokvel(id, many, contribution, startTime, interval),
      )
        .to.be.revertedWithCustomError(vault, "InvalidMemberCount")
        .withArgs(13)

      await vault
        .connect(operator)
        .createStokvel(id, many.slice(0, 12), contribution, startTime, interval)
      expect((await vault.getStokvel(id)).members).to.have.length(12)
    })

    it("reverts on a zero contribution", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      await expect(
        vault.connect(operator).createStokvel(id, members, 0, startTime, interval),
      ).to.be.revertedWithCustomError(vault, "ZeroContribution")
    })

    it("reverts on a zero interval", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      await expect(
        vault
          .connect(operator)
          .createStokvel(id, members, contribution, startTime, 0),
      ).to.be.revertedWithCustomError(vault, "ZeroInterval")
    })

    it("reverts on a start time in the past", async () => {
      const { vault, operator } = await loadFixture(deployFixture)
      const past = BigInt(await time.latest()) - 1n
      await expect(
        vault
          .connect(operator)
          .createStokvel(id, members, contribution, past, interval),
      )
        .to.be.revertedWithCustomError(vault, "StartTimeInPast")
        .withArgs(past)
    })
  })

  describe("updateStokvel", () => {
    async function createdFixture() {
      const f = await deployFixture()
      await f.vault
        .connect(f.operator)
        .createStokvel(id, members, contribution, f.startTime, interval)
      return f
    }

    it("replaces terms and members before the cycle starts", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      const newMembers = [members[2], member("zanele"), members[0]]
      const later = startTime + 600n

      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, newMembers, 2n * contribution, later, 60n),
      )
        .to.emit(vault, "StokvelUpdated")
        .withArgs(id, newMembers, 2n * contribution, later, 60n)

      const s = await vault.getStokvel(id)
      expect(s.members).to.deep.equal(newMembers)
      expect(s.contribution).to.equal(2n * contribution)
      expect(s.startTime).to.equal(later)
      expect(s.interval).to.equal(60n)
      // Removed member is no longer a member; kept and new ones are.
      expect(await vault.isMember(id, members[1])).to.be.false
      expect(await vault.isMember(id, member("zanele"))).to.be.true
      expect(await vault.isMember(id, members[0])).to.be.true
    })

    it("settings are fixed once the cycle starts", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      expect(await vault.hasStarted(id)).to.be.false

      await time.increaseTo(startTime)
      expect(await vault.hasStarted(id)).to.be.true

      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, members, contribution, startTime + 600n, interval),
      )
        .to.be.revertedWithCustomError(vault, "CycleStarted")
        .withArgs(id)
    })

    it("only the operator can update", async () => {
      const { vault, outsider, startTime } = await loadFixture(createdFixture)
      await expect(
        vault
          .connect(outsider)
          .updateStokvel(id, members, contribution, startTime, interval),
      ).to.be.revertedWithCustomError(vault, "AccessControlUnauthorizedAccount")
    })

    it("validates new terms the same way as create", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, [members[0]], contribution, startTime, interval),
      ).to.be.revertedWithCustomError(vault, "InvalidMemberCount")
      await expect(
        vault
          .connect(operator)
          .updateStokvel(
            id,
            [members[0], members[0]],
            contribution,
            startTime,
            interval,
          ),
      ).to.be.revertedWithCustomError(vault, "DuplicateMember")
    })

    it("reverts for an unknown stokvel", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, members, contribution, startTime, interval),
      )
        .to.be.revertedWithCustomError(vault, "StokvelNotFound")
        .withArgs(id)
    })
  })

  describe("views", () => {
    it("getStokvel and hasStarted revert for an unknown stokvel", async () => {
      const { vault } = await loadFixture(deployFixture)
      await expect(vault.getStokvel(id))
        .to.be.revertedWithCustomError(vault, "StokvelNotFound")
        .withArgs(id)
      await expect(vault.hasStarted(id)).to.be.revertedWithCustomError(
        vault,
        "StokvelNotFound",
      )
      expect(await vault.exists(id)).to.be.false
    })
  })

  describe("edge cases", () => {
    async function createdFixture() {
      const f = await deployFixture()
      await f.vault
        .connect(f.operator)
        .createStokvel(id, members, contribution, f.startTime, interval)
      return f
    }

    // --- Time boundaries -------------------------------------------------

    it("accepts a start time equal to the block time; it has started at once", async () => {
      const { vault, operator } = await loadFixture(deployFixture)
      const now = BigInt(await time.latest()) + 10n
      await time.setNextBlockTimestamp(now)
      await vault
        .connect(operator)
        .createStokvel(id, members, contribution, now, interval)

      expect(await vault.hasStarted(id)).to.be.true
      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, members, contribution, now + 600n, interval),
      ).to.be.revertedWithCustomError(vault, "CycleStarted")
    })

    it("allows an update one second before the start", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      await time.setNextBlockTimestamp(startTime - 1n)
      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, members, 2n * contribution, startTime, interval),
      ).to.emit(vault, "StokvelUpdated")
    })

    it("rejects an update at exactly the start time", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      await time.setNextBlockTimestamp(startTime)
      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, members, contribution, startTime + 600n, interval),
      ).to.be.revertedWithCustomError(vault, "CycleStarted")
    })

    it("rejects an update that moves the start time into the past", async () => {
      const { vault, operator } = await loadFixture(createdFixture)
      const past = BigInt(await time.latest()) - 1n
      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, members, contribution, past, interval),
      )
        .to.be.revertedWithCustomError(vault, "StartTimeInPast")
        .withArgs(past)
    })

    it("postponing the start keeps the terms open past the old start", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      const later = startTime + 3600n
      await vault
        .connect(operator)
        .updateStokvel(id, members, contribution, later, interval)

      await time.increaseTo(startTime)
      expect(await vault.hasStarted(id)).to.be.false
      await vault
        .connect(operator)
        .updateStokvel(id, members, contribution, later, 60n)
      expect((await vault.getStokvel(id)).interval).to.equal(60n)

      await time.increaseTo(later)
      expect(await vault.hasStarted(id)).to.be.true
    })

    // --- Member list boundaries ------------------------------------------

    it("accepts exactly 2 members", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      await vault
        .connect(operator)
        .createStokvel(id, members.slice(0, 2), contribution, startTime, interval)
      expect((await vault.getStokvel(id)).members).to.have.length(2)
    })

    it("reverts on a duplicate as the last of 12 members", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      const list = Array.from({ length: 11 }, (_, i) => member(`m${i}`))
      list.push(list[0])
      await expect(
        vault
          .connect(operator)
          .createStokvel(id, list, contribution, startTime, interval),
      )
        .to.be.revertedWithCustomError(vault, "DuplicateMember")
        .withArgs(list[0])
    })

    it("a failed create leaves no state behind", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      const bad = [members[0], members[1], members[0]]
      await expect(
        vault
          .connect(operator)
          .createStokvel(id, bad, contribution, startTime, interval),
      ).to.be.reverted

      expect(await vault.exists(id)).to.be.false
      expect(await vault.isMember(id, members[0])).to.be.false
      // The ID is still free.
      await vault
        .connect(operator)
        .createStokvel(id, members, contribution, startTime, interval)
    })

    // --- Update behaviour -------------------------------------------------

    it("a failed update leaves the old terms and members intact", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      const bad = [members[0], member("zanele"), member("zanele")]
      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, bad, 2n * contribution, startTime, interval),
      ).to.be.revertedWithCustomError(vault, "DuplicateMember")

      const s = await vault.getStokvel(id)
      expect(s.members).to.deep.equal(members)
      expect(s.contribution).to.equal(contribution)
      for (const m of members) expect(await vault.isMember(id, m)).to.be.true
      expect(await vault.isMember(id, member("zanele"))).to.be.false
    })

    it("an update can just reorder the payout order", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      const reordered = [members[2], members[0], members[1]]
      await vault
        .connect(operator)
        .updateStokvel(id, reordered, contribution, startTime, interval)

      expect((await vault.getStokvel(id)).members).to.deep.equal(reordered)
      for (const m of members) expect(await vault.isMember(id, m)).to.be.true
    })

    it("a member removed in one update can be added back in the next", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      await vault
        .connect(operator)
        .updateStokvel(id, members.slice(0, 2), contribution, startTime, interval)
      expect(await vault.isMember(id, members[2])).to.be.false

      await vault
        .connect(operator)
        .updateStokvel(id, members, contribution, startTime, interval)
      expect(await vault.isMember(id, members[2])).to.be.true
      expect((await vault.getStokvel(id)).members).to.deep.equal(members)
    })

    it("shrinking from 12 to 2 members clears every removed member", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      const twelve = Array.from({ length: 12 }, (_, i) => member(`m${i}`))
      await vault
        .connect(operator)
        .createStokvel(id, twelve, contribution, startTime, interval)
      await vault
        .connect(operator)
        .updateStokvel(id, twelve.slice(0, 2), contribution, startTime, interval)

      for (const m of twelve.slice(2)) {
        expect(await vault.isMember(id, m)).to.be.false
      }
      expect((await vault.getStokvel(id)).members).to.have.length(2)
    })

    it("an update does not touch another stokvel", async () => {
      const { vault, operator, startTime } = await loadFixture(createdFixture)
      const other = ethers.id("stokvel-43")
      const otherMembers = [member("sipho", other), member("thandi", other)]
      await vault
        .connect(operator)
        .createStokvel(other, otherMembers, 1n, startTime, 60n)

      await vault
        .connect(operator)
        .updateStokvel(id, members.slice(0, 2), 9n, startTime + 1n, 1n)

      const o = await vault.getStokvel(other)
      expect(o.members).to.deep.equal(otherMembers)
      expect(o.contribution).to.equal(1n)
      expect(o.interval).to.equal(60n)
    })

    // --- Value boundaries -------------------------------------------------

    it("accepts the smallest contribution and interval (1)", async () => {
      const { vault, operator, startTime } = await loadFixture(deployFixture)
      await vault.connect(operator).createStokvel(id, members, 1n, startTime, 1n)
      const s = await vault.getStokvel(id)
      expect(s.contribution).to.equal(1n)
      expect(s.interval).to.equal(1n)
    })

    // --- Roles ------------------------------------------------------------

    it("the admin can hand the operator role to a new Treasury Wallet", async () => {
      const { vault, admin, operator, outsider, startTime } =
        await loadFixture(deployFixture)
      const OPERATOR = await vault.OPERATOR_ROLE()
      await vault.connect(admin).grantRole(OPERATOR, outsider.address)
      await vault.connect(admin).revokeRole(OPERATOR, operator.address)

      await vault
        .connect(outsider)
        .createStokvel(id, members, contribution, startTime, interval)
      await expect(
        vault
          .connect(operator)
          .updateStokvel(id, members, contribution, startTime, interval),
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

