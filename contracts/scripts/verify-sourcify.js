// Verify the deployed StokvelVault on Sourcify (API v2) (#218).
// hardhat-verify's Sourcify support still calls the removed v1 API, and the
// XRPL EVM explorer's own verifier has no Solidity 0.8.24 compiler, so this
// submits the exact compiler input from the Hardhat build to Sourcify v2.
//
//   npm run verify:sourcify            uses deployments/xrplEvmTestnet.json
//
// Run `npx hardhat compile` first, from the same commit that was deployed.
const fs = require("fs")
const path = require("path")

const SOURCIFY = "https://sourcify.dev/server"
const root = path.join(__dirname, "..")
const record = JSON.parse(
  fs.readFileSync(path.join(root, "deployments", "xrplEvmTestnet.json"), "utf8"),
)
const artifactDir = path.join(root, "artifacts", "src", "StokvelVault.sol")
const dbg = JSON.parse(
  fs.readFileSync(path.join(artifactDir, "StokvelVault.dbg.json"), "utf8"),
)
const buildInfo = JSON.parse(
  fs.readFileSync(path.join(artifactDir, dbg.buildInfo), "utf8"),
)

async function main() {
  const res = await fetch(
    `${SOURCIFY}/v2/verify/${record.chainId}/${record.address}`,
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "user-agent": "remitx-contracts (github.com/Katlego-Sekoele/RemitX)",
      },
      body: JSON.stringify({
        stdJsonInput: buildInfo.input,
        compilerVersion: buildInfo.solcLongVersion,
        contractIdentifier: "src/StokvelVault.sol:StokvelVault",
        creationTransactionHash: record.transactionHash,
      }),
    },
  )
  const body = await res.json()
  if (!body.verificationId) {
    // 409 means it is already verified.
    console.log(res.status, JSON.stringify(body))
    process.exit(res.status === 409 ? 0 : 1)
  }
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 4000))
    const job = await (
      await fetch(`${SOURCIFY}/v2/verify/${body.verificationId}`)
    ).json()
    if (job.isJobCompleted) {
      if (job.error) {
        console.error("Sourcify:", JSON.stringify(job.error))
        process.exit(1)
      }
      console.log(
        `Verified on Sourcify: ${job.contract.match} ` +
          `(creation ${job.contract.creationMatch}, runtime ${job.contract.runtimeMatch})`,
      )
      console.log(
        `https://repo.sourcify.dev/${record.chainId}/${record.address}`,
      )
      return
    }
  }
  console.error("Sourcify did not finish in time; check again later.")
  process.exit(1)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
