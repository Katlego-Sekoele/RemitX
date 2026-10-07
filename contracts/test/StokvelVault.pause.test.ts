import { expect } from "chai"
import { ethers } from "hardhat"
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers"

// #199: pause and resume.

const id = ethers.id("stokvel-42")
const SERVER_SECRET = ethers.toUtf8Bytes("test-only-member-id-secret")
const member = (userId: string, stokvelId: string = id) =>
  ethers.computeHmac(
    "sha256",
    SERVER_SECRET,
    ethers.concat([stokvelId, ethers.toUtf8Bytes(userId)]),
  )
const [sipho, thandi, lerato] = ["sipho", "thandi", "lerato"].map((u) =>
  member(u),
)
const members = [sipho, thandi, lerato]
const contribution = ethers.parseUnits("500", 18)
const pool = 3n * contribution
const interval = 300n

async function startedFixture() {
  const [admin, operator, outsider, releaseTarget] = await ethers.getSigners()
  const token = await ethers.deployContract("MockUCTUSD")
  const vault = await ethers.deployContract("StokvelVault", [
    admin.address,
    operator.address,
    await token.getAddress(),
    releaseTarget.address,
  ])
  await token.mint(operator.address, ethers.parseUnits("1000000", 18))
  await token
    .connect(operator)
    .approve(await vault.getAddress(), ethers.MaxUint256)

  const startTime = BigInt(await time.latest()) + 60n
  await vault
    .connect(operator)
    .createStokvel(id, members, contribution, startTime, interval)
  await time.increaseTo(startTime)
  return { vault, token, admin, operator, outsider, releaseTarget }
}

/** Round 0 full, round 1 one short (Lerato), so her payment would finalise. */
async function oneShortFixture() {
  const f = await startedFixture()
  const op = f.vault.connect(f.operator)
  for (const m of members) await op.contribute(id, 0, m, contribution)
  await op.contribute(id, 1, sipho, contribution)
  await op.contribute(id, 1, thandi, contribution)
  return f
}

async function snapshot(
  f: Awaited<ReturnType<typeof startedFixture>>,
) {
  const s = await f.vault.getStokvel(id)
  return {
    currentRound: s.currentRound,
    closed: s.closed,
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
      expect(await vault.paused()).to.be.false

      await expect(vault.connect(admin).pause())
        .to.emit(vault, "Paused")
        .withArgs(admin.address)
      expect(await vault.paused()).to.be.true

      await expect(vault.connect(admin).unpause())
        .to.emit(vault, "Unpaused")
        .withArgs(admin.address)
      expect(await vault.paused()).to.be.false
    })

    it("the operator and ordinary accounts cannot pause", async () => {
      const { vault, operator, outsider } = await loadFixture(startedFixture)
      for (const signer of [operator, outsider]) {
        await expect(
          vault.connect(signer).pause(),
        ).to.be.revertedWithCustomError(
          vault,
          "AccessControlUnauthorizedAccount",
        )
      }
    })

    it("the operator and ordinary accounts cannot resume", async () => {
      const { vault, admin, operator, outsider } =
        await loadFixture(startedFixture)
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

    it("cannot deploy with the same key as admin and operator", async () => {
      const [a, , token, target] = await ethers.getSigners()
      const Vault = await ethers.getContractFactory("StokvelVault")
      await expect(
        ethers.deployContract("StokvelVault", [
          a.address,
          a.address,
          token.address,
          target.address,
        ]),
      ).to.be.revertedWithCustomError(Vault, "AdminIsOperator")
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
    it("runs the ticket's example", async () => {
      const f = await loadFixture(oneShortFixture)
      const { vault, admin, operator } = f
      const op = vault.connect(operator)
      const before = await snapshot(f)

      await vault.connect(admin).pause()
      // Lerato's payment would complete round 1 and finalise round 0.
      await expect(
        op.contribute(id, 1, lerato, contribution),
      ).to.be.revertedWithCustomError(vault, "EnforcedPause")

      await vault.connect(admin).unpause()
      expect(await snapshot(f)).to.deep.equal(before)
      await expect(op.contribute(id, 1, lerato, contribution))
        .to.emit(vault, "RoundFinalised")
        .withArgs(id, 0, sipho, pool)
    })

    it("every token-moving call reverts and no tokens move", async () => {
      const f = await loadFixture(oneShortFixture)
      const op = f.vault.connect(f.operator)
      const before = await snapshot(f)
      await f.vault.connect(f.admin).pause()

      // A plain contribution, and one that would trigger finalisation.
      await expect(
        op.contribute(id, 1, lerato, contribution),
      ).to.be.revertedWithCustomError(f.vault, "EnforcedPause")

      const fresh = ethers.id("stokvel-fresh")
      const pair = [member("a", fresh), member("b", fresh)]
      await op.createStokvel(fresh, pair, contribution, await time.latest() + 1, 60)
      await expect(
        op.contribute(fresh, 0, pair[0], contribution),
      ).to.be.revertedWithCustomError(f.vault, "EnforcedPause")

      expect(await snapshot(f)).to.deep.equal(before)
    })

    it("pause is checked before anything else, even for bad input", async () => {
      const { vault, admin, operator } = await loadFixture(startedFixture)
      await vault.connect(admin).pause()
      await expect(
        vault
          .connect(operator)
          .contribute(ethers.id("nope"), 9, member("x"), 1n),
      ).to.be.revertedWithCustomError(vault, "EnforcedPause")
    })

    it("views keep working so the backend can show state", async () => {
      const { vault, admin } = await loadFixture(oneShortFixture)
      await vault.connect(admin).pause()
      expect(await vault.paused()).to.be.true
      expect((await vault.getStokvel(id)).currentRound).to.equal(0)
      expect(await vault.openRound(id)).to.equal(1)
      expect(await vault.nextRecipient(id)).to.equal(sipho)
      expect(await vault.paid(id, 1, lerato)).to.be.false
    })

    it("creating and updating stokvels still work (no tokens move)", async () => {
      const { vault, admin, operator } = await loadFixture(startedFixture)
      await vault.connect(admin).pause()
      const later = ethers.id("stokvel-later")
      const pair = [member("a", later), member("b", later)]
      const start = BigInt(await time.latest()) + 3600n
      await vault
        .connect(operator)
        .createStokvel(later, pair, contribution, start, interval)
      await vault
        .connect(operator)
        .updateStokvel(later, pair, 2n * contribution, start, interval)
      expect((await vault.getStokvel(later)).contribution).to.equal(
        2n * contribution,
      )
    })
  })

  describe("after resuming", () => {
    it("payout conditions are unchanged: no early finalisation", async () => {
      const f = await loadFixture(oneShortFixture)
      const op = f.vault.connect(f.operator)
      await f.vault.connect(f.admin).pause()
      // Time passes during the pause; deadlines are informational.
      await time.increase(interval * 10n)
      await f.vault.connect(f.admin).unpause()

      // Still one short: nothing finalised on resume.
      const s = await f.vault.getStokvel(id)
      expect(s.currentRound).to.equal(0)
      expect(await f.vault.paidCount(id, 1)).to.equal(2)
      expect(await f.token.balanceOf(f.releaseTarget.address)).to.equal(0)
      expect(await f.vault.queryFilter(f.vault.filters.RoundFinalised())).to.be
        .empty

      // Rules still apply in full after resuming.
      await expect(
        op.contribute(id, 1, sipho, contribution),
      ).to.be.revertedWithCustomError(f.vault, "AlreadyPaid")
      await expect(
        op.contribute(id, 2, sipho, contribution),
      ).to.be.revertedWithCustomError(f.vault, "RoundNotOpen")
    })

    it("a full cycle completes across several pauses", async () => {
      const { vault, token, admin, operator, releaseTarget } =
        await loadFixture(startedFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) {
        for (const m of members) {
          await vault.connect(admin).pause()
          await vault.connect(admin).unpause()
          await op.contribute(id, r, m, contribution)
        }
      }
      expect((await vault.getStokvel(id)).closed).to.be.true
      expect(await token.balanceOf(releaseTarget.address)).to.equal(3n * pool)
    })
  })
})

