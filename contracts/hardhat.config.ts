import { HardhatUserConfig } from "hardhat/config"
import "@nomicfoundation/hardhat-toolbox"

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      // Paris avoids PUSH0/MCOPY so the bytecode runs on any EVM chain,
      // including the XRPL EVM Testnet.
      evmVersion: "paris",
    },
  },
  paths: {
    sources: "./src",
    tests: "./test",
  },
}

export default config
