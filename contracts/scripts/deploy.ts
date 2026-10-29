import fs from "fs"
import path from "path"
import { ethers, network } from "hardhat"

// Deploy StokvelVault (#218).
//
//   npm run deploy:local     dry run on the in-process Hardhat network
//                            (writes nothing)
//   npm run deploy:testnet   XRPL EVM Testnet
//   --network localhost      a running `npx hardhat node`: real local deploy
//                            with a mock token; writes deployments/localhost.json
//
// Testnet settings (names from docs/stokvel_integration.md §2):
//   DEPLOYER_PRIVATE_KEY     in contracts/.env (NOT the repo-root .env, which
//                            docker compose loads into the app); becomes the
//                            contract admin
//   the rest below           repo-root .env
//   EVM_TREASURY_ADDRESS     Treasury Wallet; operator and release target (D2)
//   UCTUSD_CONTRACT_ADDRESS  optional, defaults to the brief's UCTUSD address
//   MAX_STOKVEL_MEMBERS      optional, defaults to 3 (DEC-3)
//   FORCE_REDEPLOY=1         optional, replace an existing deployment record
//
// A blank value (e.g. `MAX_STOKVEL_MEMBERS=`) counts as unset and falls back
// to the default.

const DEFAULT_UCTUSD = "0x7055071C7B79A859d9514e62833BFf041ce71074"
// Local chains get a mock token and a local stand-in Treasury.
const LOCAL = network.name === "hardhat" || network.name === "localhost"
// Only the in-process Hardhat network vanishes when the script ends, so only
// it is a dry run; a localhost node keeps the contract, so it gets a record.
const DRY_RUN = network.name === "hardhat"

/** The env value, or the default when it is unset or blank. */
function env(name: string, fallback?: string): string | undefined {
  const value = process.env[name]?.trim()
  return value ? value : fallback
}

function fail(message: string): never {
  console.error(`\n✗ ${message}\n`)
  process.exit(1)
}

function requireAddress(name: string, value: string | undefined): string {
  if (!value) fail(`${name} is not set in the repo-root .env`)
  if (!ethers.isAddress(value)) fail(`${name} is not a valid address: ${value}`)
  return ethers.getAddress(value)
}

async function main() {
  const [deployer, localTreasury] = await ethers.getSigners()
  if (!deployer) fail("No deployer account. Set DEPLOYER_PRIVATE_KEY in contracts/.env")

  const { chainId } = await ethers.provider.getNetwork()
  const maxMembers = Number(env("MAX_STOKVEL_MEMBERS", "3"))
  if (!Number.isInteger(maxMembers) || maxMembers < 2 || maxMembers > 255) {
    fail(`MAX_STOKVEL_MEMBERS must be a whole number from 2 to 255, got ${maxMembers}`)
  }

  let treasury: string
  let tokenAddress: string
  if (LOCAL) {
    // Dry run: a mock token and a local account standing in for the Treasury.
    const mock = await ethers.deployContract("MockUCTUSD")
    await mock.waitForDeployment()
    tokenAddress = await mock.getAddress()
    treasury = localTreasury.address
  } else {
    treasury = requireAddress("EVM_TREASURY_ADDRESS", env("EVM_TREASURY_ADDRESS"))
    tokenAddress = requireAddress(
      "UCTUSD_CONTRACT_ADDRESS",
      env("UCTUSD_CONTRACT_ADDRESS", DEFAULT_UCTUSD),
    )
  }

  // --- Pre-flight checks ---------------------------------------------------
  if (deployer.address === treasury) {
    fail("The deployer and the Treasury Wallet must be different addresses (#218)")
  }
  if ((await ethers.provider.getCode(tokenAddress)) === "0x") {
    fail(`No contract at the UCTUSD address ${tokenAddress} on chain ${chainId}`)
  }
  const token = await ethers.getContractAt(
    ["function symbol() view returns (string)", "function decimals() view returns (uint8)"],
    tokenAddress,
  )
  const [symbol, decimals] = [await token.symbol(), await token.decimals()]
  if (Number(decimals) !== 18) fail(`Expected an 18-decimal token, ${symbol} has ${decimals}`)

  const balance = await ethers.provider.getBalance(deployer.address)
  if (balance === 0n) {
    fail(
      `Deployer ${deployer.address} has no test XRP for gas.\n` +
        "  Fund it from the XRPL EVM faucet (Testnet) first (#224).",
    )
  }

  const recordPath = path.join(__dirname, "..", "deployments", `${network.name}.json`)
  if (!DRY_RUN && fs.existsSync(recordPath) && env("FORCE_REDEPLOY") !== "1") {
    fail(
      `${path.relative(process.cwd(), recordPath)} already exists. ` +
        "Set FORCE_REDEPLOY=1 to deploy a new contract and replace it.",
    )
  }

  const args = [deployer.address, treasury, tokenAddress, treasury, maxMembers] as const
  console.log(`Network        ${network.name} (chain ${chainId})`)
  console.log(`Deployer/admin ${deployer.address} (${ethers.formatEther(balance)} XRP)`)
  console.log(`Operator       ${treasury} (Treasury Wallet)`)
  console.log(`Release target ${treasury} (Treasury Wallet)`)
  console.log(`Token          ${tokenAddress} (${symbol}, ${decimals} decimals)`)
  console.log(`maxMembers     ${maxMembers}\n`)

  // --- Deploy ---------------------------------------------------------------
  const vault = await ethers.deployContract("StokvelVault", [...args])
  const tx = vault.deploymentTransaction()!
  console.log(`Deploying... tx ${tx.hash}`)
  await vault.waitForDeployment()
  const receipt = await tx.wait(LOCAL ? 1 : 2)
  const address = await vault.getAddress()

  // The contract now exists on-chain whatever happens next, so say where it
  // is and record it before checking it.
  console.log(`\nStokvelVault deployed at ${address} (block ${receipt!.blockNumber})`)
  const record: Record<string, unknown> = {
    network: network.name,
    chainId: Number(chainId),
    contract: "StokvelVault",
    address,
    blockNumber: receipt!.blockNumber,
    transactionHash: tx.hash,
    deployedAt: new Date().toISOString(),
    constructorArgs: {
      admin: deployer.address,
      operator: treasury,
      token: tokenAddress,
      releaseTarget: treasury,
      maxMembers,
    },
  }
  const writeRecord = () => {
    if (DRY_RUN) return
    fs.mkdirSync(path.dirname(recordPath), { recursive: true })
    fs.writeFileSync(recordPath, JSON.stringify(record, null, 2) + "\n")
  }
  writeRecord()

  // --- Post-deploy checks ---------------------------------------------------
  const checks: [string, boolean][] = [
    ["admin role on deployer", await vault.hasRole(await vault.DEFAULT_ADMIN_ROLE(), deployer.address)],
    ["operator role on Treasury", await vault.hasRole(await vault.OPERATOR_ROLE(), treasury)],
    ["Treasury is not admin", !(await vault.hasRole(await vault.DEFAULT_ADMIN_ROLE(), treasury))],
    ["token", (await vault.token()) === tokenAddress],
    ["release target", (await vault.releaseTarget()) === treasury],
    ["maxMembers", Number(await vault.maxMembers()) === maxMembers],
    ["not paused", !(await vault.paused())],
  ]
  for (const [name, ok] of checks) console.log(`${ok ? "✓" : "✗"} ${name}`)
  const failed = checks.filter(([, ok]) => !ok).map(([name]) => name)
  record.postDeployChecks = failed.length === 0 ? "passed" : { failed }
  writeRecord()

  if (DRY_RUN) {
    console.log("\nDry run only: nothing was written.")
  } else {
    console.log(`\nWrote ${path.relative(process.cwd(), recordPath)}`)
  }
  if (failed.length > 0) {
    fail(
      `Post-deploy checks failed: ${failed.join(", ")}.\n` +
        `  The contract IS deployed at ${address}` +
        (DRY_RUN ? "." : " and recorded; do not use it. Fix the cause, then redeploy with FORCE_REDEPLOY=1."),
    )
  }
  if (DRY_RUN || network.name === "localhost") return

  console.log("\nNext:")
  console.log(`  1. Add to .env and .env.example:  STOKVEL_CONTRACT_ADDRESS=${address}`)
  console.log("  2. Verify the source:  npm run verify:sourcify")
  console.log(`  3. Explorer: https://explorer.testnet.xrplevm.org/address/${address}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
