import path from "path"
import dotenv from "dotenv"
import { HardhatUserConfig } from "hardhat/config"
import "@nomicfoundation/hardhat-toolbox"

// The repo-root .env is the single source of config (see CLAUDE.md).
dotenv.config({ path: path.resolve(__dirname, "../.env") })

// Defaults are the public values from docs/stokvel_integration.md section 2.
const EVM_RPC_URL = process.env.EVM_RPC_URL ?? "https://rpc.testnet.xrplevm.org"
const EVM_CHAIN_ID = Number(process.env.EVM_CHAIN_ID ?? 1449000)
// Read only from the environment, never from source control (#218).
const DEPLOYER_PRIVATE_KEY = process.env.DEPLOYER_PRIVATE_KEY

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
  networks: {
    xrplEvmTestnet: {
      url: EVM_RPC_URL,
      chainId: EVM_CHAIN_ID,
      accounts: DEPLOYER_PRIVATE_KEY ? [DEPLOYER_PRIVATE_KEY] : [],
    },
  },
  // Source verification on the XRPL EVM Testnet explorer (Blockscout).
  etherscan: {
    apiKey: { xrplEvmTestnet: "blockscout" },
    customChains: [
      {
        network: "xrplEvmTestnet",
        chainId: EVM_CHAIN_ID,
        urls: {
          apiURL: "https://explorer.testnet.xrplevm.org/api",
          browserURL: "https://explorer.testnet.xrplevm.org",
        },
      },
    ],
  },
  sourcify: { enabled: false },
}

export default config
