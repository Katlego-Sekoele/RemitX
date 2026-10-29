// Copy StokvelVault's ABI from the Hardhat build into contracts/abi/, the
// committed file the backend loads (#219). Run via `npm run export:abi`,
// which compiles first. test/abi.test.ts fails if the two drift apart.
const fs = require("fs")
const path = require("path")

const artifact = path.join(
  __dirname,
  "..",
  "artifacts",
  "src",
  "StokvelVault.sol",
  "StokvelVault.json",
)
const out = path.join(__dirname, "..", "abi", "StokvelVault.json")

const { abi } = JSON.parse(fs.readFileSync(artifact, "utf8"))
fs.mkdirSync(path.dirname(out), { recursive: true })
fs.writeFileSync(out, JSON.stringify(abi, null, 2) + "\n")
console.log(`Wrote ${path.relative(process.cwd(), out)} (${abi.length} entries)`)
