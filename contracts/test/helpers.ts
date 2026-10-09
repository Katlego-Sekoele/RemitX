import { ethers } from "hardhat"
import { time } from "@nomicfoundation/hardhat-network-helpers"

/**
 * Database UUID -> bytes32, left-aligned: the 16 UUID bytes first, the rest
 * zero (doc section 1). The backend must use the same packing.
 */
export function uuidToBytes32(uuid: string): string {
  const hex = uuid.replace(/-/g, "").toLowerCase()
  if (!/^[0-9a-f]{32}$/.test(hex)) throw new Error(`not a UUID: ${uuid}`)
  return "0x" + hex + "0".repeat(32)
}

export const STOKVEL_ID = uuidToBytes32("5f0c2a1e-8d3b-4c6a-9e71-2b4f6d8a0c13")
// stokvel_members row UUIDs (per stokvel), not user IDs.
export const SIPHO = uuidToBytes32("a1b2c3d4-0000-4000-8000-000000000001")
export const THANDI = uuidToBytes32("a1b2c3d4-0000-4000-8000-000000000002")
export const LERATO = uuidToBytes32("a1b2c3d4-0000-4000-8000-000000000003")
export const MEMBERS = [SIPHO, THANDI, LERATO]

export const CONTRIBUTION = ethers.parseUnits("500", 18)
export const POOL = 3n * CONTRIBUTION
export const INTERVAL = 300n // 5 minutes between rounds for the demo
export const MAX_MEMBERS = 3

export function memberId(n: number): string {
  return uuidToBytes32(
    `a1b2c3d4-0000-4000-8000-${n.toString(16).padStart(12, "0")}`,
  )
}

/**
 * Round i starts at first + i*interval, its deadline is halfway through,
 * and its payout time is at the end of the round.
 */
export function schedule(first: bigint, rounds: number, interval = INTERVAL) {
  const starts: bigint[] = []
  const deadlines: bigint[] = []
  const payouts: bigint[] = []
  for (let i = 0; i < rounds; i++) {
    const start = first + BigInt(i) * interval
    starts.push(start)
    deadlines.push(start + interval / 2n)
    payouts.push(start + interval)
  }
  return { starts, deadlines, payouts }
}

export async function deploy(
  tokenName = "MockUCTUSD",
  maxMembers = MAX_MEMBERS,
) {
  const [admin, operator, outsider, releaseTarget] = await ethers.getSigners()
  const token = await ethers.deployContract(tokenName)
  const vault = await ethers.deployContract("StokvelVault", [
    admin.address,
    operator.address,
    await token.getAddress(),
    releaseTarget.address,
    maxMembers,
  ])
  // The Treasury Wallet holds float and lets the vault pull contributions.
  await token.mint(operator.address, ethers.parseUnits("1000000", 18))
  await token
    .connect(operator)
    .approve(await vault.getAddress(), ethers.MaxUint256)
  return { vault, token, admin, operator, outsider, releaseTarget }
}

/** Stokvel created and its first 3-member cycle started; round 0 open now. */
export async function startedFixture() {
  const f = await deploy()
  const first = BigInt(await time.latest()) + 1n
  const sched = schedule(first, MEMBERS.length)
  await f.vault.connect(f.operator).createStokvel(STOKVEL_ID, CONTRIBUTION)
  await f.vault
    .connect(f.operator)
    .startCycle(
      STOKVEL_ID,
      MEMBERS,
      sched.starts,
      sched.deadlines,
      sched.payouts,
    )
  return { ...f, sched }
}

type Vault = Awaited<ReturnType<typeof deploy>>["vault"]

/** Every member pays `round`, in order. Returns the last transaction. */
export async function payRound(
  op: Vault,
  round: number,
  members: string[] = MEMBERS,
  id = STOKVEL_ID,
) {
  let tx
  for (const m of members) tx = await op.contribute(id, round, m)
  return tx!
}
