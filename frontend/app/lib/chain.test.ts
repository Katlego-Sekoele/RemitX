import { assert, test } from "vitest"

import {
  chainOfHash,
  EVM_EXPLORER_URL,
  explorerAddressUrl,
  explorerTxUrl,
  shortHash,
} from "./chain"

const EVM_HASH = `0x51a0${"c".repeat(56)}9b0e`
const XRPL_HASH = `A1B2${"0".repeat(56)}9F0E`

test("chainOfHash tells EVM hashes from XRPL ones by the 0x prefix", () => {
  assert.equal(chainOfHash(EVM_HASH), "evm")
  assert.equal(chainOfHash(EVM_HASH.toUpperCase().replace("0X", "0x")), "evm")
  assert.equal(chainOfHash(XRPL_HASH), "xrpl")
})

test("explorerTxUrl links each hash to its own explorer", () => {
  assert.equal(
    explorerTxUrl(EVM_HASH),
    `https://explorer.testnet.xrplevm.org/tx/${EVM_HASH}`
  )
  assert.equal(
    explorerTxUrl(` ${XRPL_HASH} `),
    `https://testnet.xrpl.org/transactions/${XRPL_HASH}`
  )
  assert.notMatch(EVM_EXPLORER_URL, /\/$/)
})

test("explorerAddressUrl is on the EVM explorer", () => {
  assert.equal(
    explorerAddressUrl("0x2f240705314BB79780522635eA47d20072CB8Fe1"),
    "https://explorer.testnet.xrplevm.org/address/0x2f240705314BB79780522635eA47d20072CB8Fe1"
  )
})

test("shortHash keeps the 0x so the two chains read differently", () => {
  assert.equal(shortHash(EVM_HASH), "0x51a0…9b0e")
  assert.equal(shortHash(XRPL_HASH), "A1B2…9F0E")
  assert.equal(shortHash("ABC"), "ABC")
  assert.equal(shortHash("0xabc"), "0xabc")
})
