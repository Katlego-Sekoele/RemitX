import { expect } from "chai"
import fs from "fs"
import path from "path"
import { artifacts } from "hardhat"

// The backend loads contracts/abi/StokvelVault.json (#219). Fail if it no
// longer matches the compiled contract: run `npm run export:abi` to fix.
describe("StokvelVault: exported ABI", () => {
  it("matches the compiled contract", async () => {
    const compiled = (await artifacts.readArtifact("StokvelVault")).abi
    const file = path.join(__dirname, "..", "abi", "StokvelVault.json")
    expect(fs.existsSync(file), "abi/StokvelVault.json is missing").to.be.true
    const exported = JSON.parse(fs.readFileSync(file, "utf8"))
    expect(exported).to.deep.equal(compiled)
  })
})
