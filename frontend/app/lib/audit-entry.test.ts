import { assert, test } from "vitest"

import { auditTxHash, isStokvelEntry } from "./audit-entry"

const HASH = `0x${"ab".repeat(32)}`

test("auditTxHash finds an EVM hash under any *tx_hash key", () => {
  assert.equal(
    auditTxHash({ after: { release_tx_hash: HASH }, before: null }),
    HASH
  )
  assert.equal(auditTxHash({ after: null, before: { tx_hash: HASH } }), HASH)
  // `after` wins over `before`.
  const other = `0x${"cd".repeat(32)}`
  assert.equal(
    auditTxHash({ after: { tx_hash: HASH }, before: { tx_hash: other } }),
    HASH
  )
})

test("auditTxHash ignores anything that isn't an EVM hash", () => {
  assert.equal(auditTxHash({ after: null, before: null }), null)
  assert.equal(auditTxHash({ after: { paused: true }, before: null }), null)
  assert.equal(
    auditTxHash({ after: { tx_hash: "pending" }, before: null }),
    null
  )
  assert.equal(auditTxHash({ after: { tx_hash: "ABCD" }, before: null }), null)
  assert.equal(auditTxHash({ after: { hash: HASH }, before: null }), null)
})

test("isStokvelEntry spots stokvel subjects and actions", () => {
  assert.equal(
    isStokvelEntry({ subject_type: "stokvel_contract", action: "x" }),
    true
  )
  assert.equal(isStokvelEntry({ subject_type: "stokvel", action: "x" }), true)
  assert.equal(
    isStokvelEntry({
      subject_type: "something",
      action: "stokvel.round.finalised_manually",
    }),
    true
  )
  assert.equal(
    isStokvelEntry({
      subject_type: "kyc_application",
      action: "kyc.pii.viewed",
    }),
    false
  )
})
