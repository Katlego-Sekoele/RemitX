import { assert, test } from "vitest"

import {
  contributeRefusal,
  contributeRefusalMessage,
  isFinalRefusal,
  stokvelErrorCode,
  stokvelErrorMessage,
} from "./stokvel-errors"

function apiError(message: string, status: number, body?: unknown) {
  return Object.assign(new Error(message), { name: "ApiError", status, body })
}

test("codes are read from the body, then the detail, then the message", () => {
  assert.equal(
    stokvelErrorCode(apiError("x", 409, { code: "contribution_already_paid" })),
    "contribution_already_paid"
  )
  assert.equal(
    stokvelErrorCode(apiError("x", 503, { detail: "stokvel_paused" })),
    "stokvel_paused"
  )
  assert.equal(
    stokvelErrorCode(apiError("x", 409, { detail: { code: "wrong_round" } })),
    "wrong_round"
  )
  assert.equal(
    stokvelErrorCode(apiError("409 round_not_finalisable", 409)),
    "round_not_finalisable"
  )
  assert.equal(
    stokvelErrorCode(apiError("boom", 500, { detail: "boom" })),
    null
  )
  assert.equal(stokvelErrorCode("not an error"), null)
})

test("known codes get the doc §6 wording, others keep the API message", () => {
  assert.equal(
    stokvelErrorMessage(apiError("x", 503, { code: "treasury_funds_low" })),
    "Contributions are temporarily unavailable. Please try again later."
  )
  assert.equal(
    stokvelErrorMessage(apiError("Quote expired", 409)),
    "Quote expired"
  )
  assert.equal(stokvelErrorMessage(undefined), "Something went wrong.")
})

test("contribute refusals cover the ledger's own checks", () => {
  assert.equal(
    contributeRefusal(apiError("Amount exceeds your available balance", 400)),
    "insufficient_balance"
  )
  assert.equal(
    contributeRefusal(apiError("Over your monthly limit by R20", 400)),
    "over_limit"
  )
  assert.equal(contributeRefusal(apiError("Forbidden", 403)), "unverified")
  assert.equal(
    contributeRefusal(
      apiError("x", 409, { code: "contribution_already_paid" })
    ),
    "contribution_already_paid"
  )
  assert.equal(contributeRefusal(apiError("Server error", 500)), "other")
  assert.match(
    contributeRefusalMessage("insufficient_balance", undefined),
    /Top up first/
  )
  assert.equal(
    contributeRefusalMessage("other", apiError("Server error", 500)),
    "Server error"
  )
})

test("final refusals are the ones a retry cannot fix", () => {
  assert.ok(isFinalRefusal("contribution_already_paid"))
  assert.ok(isFinalRefusal("cycle_not_open"))
  assert.ok(!isFinalRefusal("stokvel_paused"))
  assert.ok(!isFinalRefusal("insufficient_balance"))
})
