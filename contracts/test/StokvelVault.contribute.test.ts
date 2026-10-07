import { expect } from "chai"
import { ethers } from "hardhat"
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers"

// #198: contributions and finalisation.

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

async function deploy(tokenName: "MockUCTUSD" | "ReentrantToken") {
  const [admin, operator, outsider, releaseTarget] = await ethers.getSigners()
  const token = await ethers.deployContract(tokenName)
  const vault = await ethers.deployContract("StokvelVault", [
    admin.address,
    operator.address,
    await token.getAddress(),
    releaseTarget.address,
  ])
  // The Treasury Wallet holds float and lets the vault pull contributions.
  await token.mint(operator.address, ethers.parseUnits("1000000", 18))
  await token
    .connect(operator)
    .approve(await vault.getAddress(), ethers.MaxUint256)

  const startTime = BigInt(await time.latest()) + 60n
  await vault
    .connect(operator)
    .createStokvel(id, members, contribution, startTime, interval)
  await time.increaseTo(startTime)
  return { vault, token, admin, operator, outsider, releaseTarget, startTime }
}

const startedFixture = () => deploy("MockUCTUSD")
const reentrantFixture = () => deploy("ReentrantToken")

describe("StokvelVault: contributions and finalisation", () => {
  it("runs the ticket's example sequence", async () => {
    const { vault, token, operator, releaseTarget } =
      await loadFixture(startedFixture)
    const op = vault.connect(operator)

    await expect(op.contribute(id, 0, sipho, contribution))
      .to.emit(vault, "ContributionMade")
      .withArgs(id, 0, sipho, contribution)
    expect(await vault.paidCount(id, 0)).to.equal(1)

    await expect(op.contribute(id, 0, sipho, contribution))
      .to.be.revertedWithCustomError(vault, "AlreadyPaid")
      .withArgs(id, 0, sipho)

    await op.contribute(id, 0, thandi, contribution)
    await expect(op.contribute(id, 0, lerato, contribution)).to.not.emit(
      vault,
      "RoundFinalised",
    )
    expect(await vault.paidCount(id, 0)).to.equal(3)
    expect(await vault.openRound(id)).to.equal(1)

    await op.contribute(id, 1, sipho, contribution)
    await op.contribute(id, 1, thandi, contribution)
    const tx = op.contribute(id, 1, lerato, contribution)
    await expect(tx)
      .to.emit(vault, "RoundFinalised")
      .withArgs(id, 0, sipho, pool)
    await expect(tx).to.changeTokenBalances(
      token,
      [releaseTarget, vault],
      [pool, contribution - pool],
    )

    const s = await vault.getStokvel(id)
    expect(s.currentRound).to.equal(1)
    expect(s.closed).to.be.false
    expect(await vault.roundPool(id, 0)).to.equal(0)
    expect(await vault.roundPool(id, 1)).to.equal(pool)
    expect(await vault.nextRecipient(id)).to.equal(thandi)
  })

  describe("reverts", () => {
    it("on a wrong amount, too low or too high", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      for (const amount of [contribution - 1n, contribution + 1n, 0n]) {
        await expect(
          vault.connect(operator).contribute(id, 0, sipho, amount),
        )
          .to.be.revertedWithCustomError(vault, "WrongAmount")
          .withArgs(contribution, amount)
      }
    })

    it("on an unknown member, including a member of another stokvel", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const other = ethers.id("stokvel-43")
      for (const m of [member("nobody"), member("sipho", other)]) {
        await expect(vault.connect(operator).contribute(id, 0, m, contribution))
          .to.be.revertedWithCustomError(vault, "NotMember")
          .withArgs(id, m)
      }
    })

    it("on an unauthorised sender", async () => {
      const { vault, token, admin, outsider } =
        await loadFixture(startedFixture)
      await token.mint(outsider.address, contribution)
      await token
        .connect(outsider)
        .approve(await vault.getAddress(), contribution)
      for (const signer of [admin, outsider]) {
        await expect(
          vault.connect(signer).contribute(id, 0, sipho, contribution),
        ).to.be.revertedWithCustomError(
          vault,
          "AccessControlUnauthorizedAccount",
        )
      }
    })

    it("on an unknown stokvel", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const unknown = ethers.id("stokvel-404")
      await expect(
        vault.connect(operator).contribute(unknown, 0, sipho, contribution),
      )
        .to.be.revertedWithCustomError(vault, "StokvelNotFound")
        .withArgs(unknown)
    })

    it("before the cycle starts, while terms can still change", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const later = ethers.id("stokvel-later")
      const start = BigInt(await time.latest()) + 3600n
      const laterMembers = [member("a", later), member("b", later)]
      await vault
        .connect(operator)
        .createStokvel(later, laterMembers, contribution, start, interval)

      await expect(
        vault
          .connect(operator)
          .contribute(later, 0, laterMembers[0], contribution),
      )
        .to.be.revertedWithCustomError(vault, "CycleNotStarted")
        .withArgs(later)
    })

    it("on a round that is not open", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)

      // Round 1 is closed until round 0 is full.
      await op.contribute(id, 0, sipho, contribution)
      await expect(op.contribute(id, 1, thandi, contribution))
        .to.be.revertedWithCustomError(vault, "RoundNotOpen")
        .withArgs(1, 0)

      // Once round 0 is full, it no longer accepts anything.
      await op.contribute(id, 0, thandi, contribution)
      await op.contribute(id, 0, lerato, contribution)
      await expect(op.contribute(id, 0, sipho, contribution))
        .to.be.revertedWithCustomError(vault, "RoundNotOpen")
        .withArgs(0, 1)

      // Rounds further ahead, or past the cycle, are never open.
      for (const r of [2, 3, 255]) {
        await expect(op.contribute(id, r, sipho, contribution))
          .to.be.revertedWithCustomError(vault, "RoundNotOpen")
          .withArgs(r, 1)
      }
    })

    it("when the Treasury Wallet has not approved enough, leaving no state", async () => {
      const { vault, token, operator } = await loadFixture(startedFixture)
      await token
        .connect(operator)
        .approve(await vault.getAddress(), contribution - 1n)
      await expect(
        vault.connect(operator).contribute(id, 0, sipho, contribution),
      ).to.be.revertedWithCustomError(token, "ERC20InsufficientAllowance")
      expect(await vault.paid(id, 0, sipho)).to.be.false
      expect(await vault.paidCount(id, 0)).to.equal(0)
      expect(await vault.roundPool(id, 0)).to.equal(0)
    })
  })

  describe("blocked rounds and deadlines", () => {
    it("a round one member short never finalises, however late", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await op.contribute(id, 0, sipho, contribution)
      await op.contribute(id, 0, thandi, contribution)

      // Every deadline in the cycle passes; Lerato never pays.
      await time.increase(interval * 10n)

      await expect(
        op.contribute(id, 1, sipho, contribution),
      ).to.be.revertedWithCustomError(vault, "RoundNotOpen")
      const s = await vault.getStokvel(id)
      expect(s.currentRound).to.equal(0)
      expect(s.closed).to.be.false
      expect(await vault.openRound(id)).to.equal(0)
      expect(await token.balanceOf(releaseTarget)).to.equal(0)
      expect(await vault.roundPool(id, 0)).to.equal(2n * contribution)
      expect(await vault.queryFilter(vault.filters.RoundFinalised())).to.be
        .empty
    })

    it("accepts a late contribution (deadlines are informational)", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      await time.increaseTo((await vault.payoutTime(id, 0)) + 3600n)
      await expect(
        vault.connect(operator).contribute(id, 0, sipho, contribution),
      ).to.emit(vault, "ContributionMade")
    })
  })

  describe("finalisation and closing", () => {
    async function payRound(
      vault: Awaited<ReturnType<typeof startedFixture>>["vault"],
      round: number,
      list: string[] = members,
    ) {
      let tx
      for (const m of list) tx = await vault.contribute(id, round, m, contribution)
      return tx!
    }

    it("closes after the last round: the final contribution releases two pools", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(startedFixture)
      const op = vault.connect(operator)
      await payRound(op, 0)
      await payRound(op, 1) // finalises round 0

      await op.contribute(id, 2, sipho, contribution)
      await op.contribute(id, 2, thandi, contribution)
      const last = op.contribute(id, 2, lerato, contribution)
      await expect(last)
        .to.emit(vault, "RoundFinalised")
        .withArgs(id, 1, thandi, pool)
        .and.to.emit(vault, "RoundFinalised")
        .withArgs(id, 2, lerato, pool)
        .and.to.emit(vault, "StokvelClosed")
        .withArgs(id)

      const s = await vault.getStokvel(id)
      expect(s.closed).to.be.true
      expect(s.currentRound).to.equal(3)
      expect(await token.balanceOf(releaseTarget)).to.equal(3n * pool)
      expect(await token.balanceOf(await vault.getAddress())).to.equal(0)
      for (const r of [0, 1, 2]) expect(await vault.roundPool(id, r)).to.equal(0)
    })

    it("finalises each round exactly once, to the right member, in payout order", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) await payRound(op, r)

      const events = await vault.queryFilter(vault.filters.RoundFinalised(id))
      expect(events.map((e) => [Number(e.args.round), e.args.recipientId])).to
        .deep.equal([
          [0, sipho],
          [1, thandi],
          [2, lerato],
        ])
      expect(
        await vault.queryFilter(vault.filters.StokvelClosed(id)),
      ).to.have.length(1)
    })

    it("rejects any contribution once closed", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      for (const r of [0, 1, 2]) await payRound(op, r)

      for (const r of [0, 2, 3]) {
        await expect(op.contribute(id, r, sipho, contribution))
          .to.be.revertedWithCustomError(vault, "StokvelIsClosed")
          .withArgs(id)
      }
      await expect(vault.nextRecipient(id)).to.be.revertedWithCustomError(
        vault,
        "StokvelIsClosed",
      )
      await expect(vault.openRound(id)).to.be.revertedWithCustomError(
        vault,
        "StokvelIsClosed",
      )
    })

    it("a 2-member stokvel finalises both rounds when round 1 fills", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(startedFixture)
      const pair = ethers.id("stokvel-pair")
      const two = [member("a", pair), member("b", pair)]
      await vault
        .connect(operator)
        .createStokvel(pair, two, contribution, await time.latest() + 1, 60)
      const op = vault.connect(operator)
      await op.contribute(pair, 0, two[0], contribution)
      await op.contribute(pair, 0, two[1], contribution)
      await op.contribute(pair, 1, two[1], contribution)
      await expect(op.contribute(pair, 1, two[0], contribution))
        .to.emit(vault, "StokvelClosed")
        .withArgs(pair)
      expect(await token.balanceOf(releaseTarget)).to.equal(4n * contribution)
    })

    it("runs a full 12-member cycle (144 contributions) and keeps the books balanced", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(startedFixture)
      const big = ethers.id("stokvel-12")
      const twelve = Array.from({ length: 12 }, (_, i) => member(`m${i}`, big))
      await vault
        .connect(operator)
        .createStokvel(big, twelve, contribution, await time.latest() + 1, 60)
      const op = vault.connect(operator)
      const vaultAddr = await vault.getAddress()

      let maxGas = 0n
      for (let r = 0; r < 12; r++) {
        for (const m of twelve) {
          const receipt = await (
            await op.contribute(big, r, m, contribution)
          ).wait()
          if (receipt!.gasUsed > maxGas) maxGas = receipt!.gasUsed
        }
        // Vault holds exactly the pools not yet released.
        let held = 0n
        for (let k = 0; k < 12; k++) held += await vault.roundPool(big, k)
        expect(await token.balanceOf(vaultAddr)).to.equal(held)
      }

      expect((await vault.getStokvel(big)).closed).to.be.true
      expect(await token.balanceOf(releaseTarget)).to.equal(
        144n * contribution,
      )
      // Worst case is the final call (two releases); keep it well bounded.
      expect(maxGas).to.be.lessThan(300_000n)
    })
  })

  describe("reentrancy", () => {
    async function armedFixture() {
      const f = await reentrantFixture()
      // Give the token the operator role so the reentrant call gets past
      // access control and reaches the reentrancy guard.
      await f.vault
        .connect(f.admin)
        .grantRole(await f.vault.OPERATOR_ROLE(), await f.token.getAddress())
      return f
    }

    it("a token that re-enters during the pool release cannot finalise twice", async () => {
      const { vault, token, operator, releaseTarget } =
        await loadFixture(armedFixture)
      const op = vault.connect(operator)
      for (const m of members) await op.contribute(id, 0, m, contribution)
      await op.contribute(id, 1, sipho, contribution)
      await op.contribute(id, 1, thandi, contribution)

      await token.arm(
        await vault.getAddress(),
        releaseTarget.address,
        vault.interface.encodeFunctionData("contribute", [
          id,
          2,
          sipho,
          contribution,
        ]),
      )
      await expect(
        op.contribute(id, 1, lerato, contribution),
      ).to.be.revertedWithCustomError(vault, "ReentrancyGuardReentrantCall")

      // Nothing moved: the whole transaction rolled back.
      expect((await vault.getStokvel(id)).currentRound).to.equal(0)
      expect(await vault.roundPool(id, 0)).to.equal(pool)
      expect(await vault.paid(id, 1, lerato)).to.be.false
      expect(await token.balanceOf(releaseTarget)).to.equal(0)
    })

    it("a token that re-enters while contributions are pulled is blocked", async () => {
      const { vault, token, operator } = await loadFixture(armedFixture)
      await token.arm(
        await vault.getAddress(),
        await vault.getAddress(),
        vault.interface.encodeFunctionData("contribute", [
          id,
          0,
          thandi,
          contribution,
        ]),
      )
      await expect(
        vault.connect(operator).contribute(id, 0, sipho, contribution),
      ).to.be.revertedWithCustomError(vault, "ReentrancyGuardReentrantCall")
      expect(await vault.paidCount(id, 0)).to.equal(0)
    })
  })

  describe("views", () => {
    it("payoutTime is the scheduled end of each round", async () => {
      const { vault, startTime } = await loadFixture(startedFixture)
      for (const r of [0, 1, 2]) {
        expect(await vault.payoutTime(id, r)).to.equal(
          startTime + BigInt(r + 1) * interval,
        )
      }
      await expect(vault.payoutTime(id, 3))
        .to.be.revertedWithCustomError(vault, "RoundOutOfRange")
        .withArgs(3)
    })

    it("payoutTime cannot overflow with extreme terms", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const extreme = ethers.id("stokvel-extreme")
      const maxU64 = 2n ** 64n - 1n
      const list = Array.from({ length: 12 }, (_, i) => member(`m${i}`, extreme))
      await vault
        .connect(operator)
        .createStokvel(extreme, list, 1n, maxU64, maxU64)
      expect(await vault.payoutTime(extreme, 11)).to.equal(maxU64 + 12n * maxU64)
    })

    it("nextRecipient follows the payout order", async () => {
      const { vault, operator } = await loadFixture(startedFixture)
      const op = vault.connect(operator)
      expect(await vault.nextRecipient(id)).to.equal(sipho)
      for (const m of members) await op.contribute(id, 0, m, contribution)
      expect(await vault.nextRecipient(id)).to.equal(sipho)
      for (const m of members) await op.contribute(id, 1, m, contribution)
      expect(await vault.nextRecipient(id)).to.equal(thandi)
    })

    it("views revert for an unknown stokvel", async () => {
      const { vault } = await loadFixture(startedFixture)
      const unknown = ethers.id("stokvel-404")
      for (const call of [
        vault.openRound(unknown),
        vault.payoutTime(unknown, 0),
        vault.nextRecipient(unknown),
      ]) {
        await expect(call).to.be.revertedWithCustomError(
          vault,
          "StokvelNotFound",
        )
      }
    })
  })
})
