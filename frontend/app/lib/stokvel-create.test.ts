import { assert, test } from "vitest"

import {
  contributionIssue,
  createStokvelRequest,
  nameIssue,
  readCreateSearch,
  resolveCreateCurrency,
  resolveCreateStep,
  writeCreateSearch,
  type CreateSearch,
} from "./stokvel-create"

const BLANK: CreateSearch = {
  name: "",
  currency: null,
  amount: "",
  step: null,
}

// R18.25 per token: 0.05479452 token units per rand.
const RATE = "0.05479452"

test("search params round-trip and drop defaults", () => {
  const params = writeCreateSearch(BLANK, {
    name: "December groceries",
    amount: "500",
    step: "amount",
  })
  assert.equal(
    params.toString(),
    "name=December+groceries&amount=500&step=amount"
  )
  const read = readCreateSearch(params)
  assert.equal(read.name, "December groceries")
  assert.equal(read.amount, "500")
  assert.equal(read.step, "amount")
  assert.equal(read.currency, null)
})

test("a non-default currency is kept in the URL and ZAR is dropped", () => {
  assert.equal(
    readCreateSearch(writeCreateSearch(BLANK, { currency: "USD" })).currency,
    "USD"
  )
  assert.equal(writeCreateSearch(BLANK, { currency: "ZAR" }).toString(), "")
})

test("resolveCreateCurrency only accepts a currency the user holds", () => {
  assert.equal(resolveCreateCurrency("USD", ["ZAR", "USD"]), "USD")
  assert.equal(resolveCreateCurrency("XYZ", ["ZAR", "USD"]), "ZAR")
  assert.equal(resolveCreateCurrency(null, ["ZAR"]), "ZAR")
})

test("resolveCreateStep never shows a step the data cannot support", () => {
  assert.equal(
    resolveCreateStep({ ...BLANK, step: "review" }, false, true),
    "name"
  )
  assert.equal(
    resolveCreateStep({ ...BLANK, step: "review" }, true, false),
    "amount"
  )
  assert.equal(
    resolveCreateStep({ ...BLANK, step: "review" }, true, true),
    "review"
  )
  assert.equal(
    resolveCreateStep({ ...BLANK, step: "name" }, true, true),
    "name"
  )
})

test("name and amount validation", () => {
  assert.equal(nameIssue("  "), "Give the stokvel a name.")
  assert.equal(nameIssue("Taxi fund"), null)
  assert.equal(nameIssue("x".repeat(80)), null)
  assert.match(nameIssue("x".repeat(81)) ?? "", /80 characters/)
  assert.equal(contributionIssue(""), "empty")
  assert.equal(contributionIssue("abc"), "invalid")
  assert.equal(contributionIssue("0"), "invalid")
  assert.equal(contributionIssue("5"), "too_small")
  assert.equal(contributionIssue("500"), null)
})

test("the create body is exactly the API's three fields, in UCTUSD to the cent", () => {
  const body = createStokvelRequest(
    { ...BLANK, name: " Taxi fund ", amount: "500" },
    "ZAR",
    RATE
  )
  // 500 × 0.05479452 = 27.39726, rounded half up to the cent.
  assert.deepEqual(body, {
    name: "Taxi fund",
    currency: "ZAR",
    contribution_amount: "27.40",
  })
  assert.deepEqual(Object.keys(body).sort(), [
    "contribution_amount",
    "currency",
    "name",
  ])
  // 300 × 0.05479452 = 16.438356 → 16.44.
  assert.equal(
    createStokvelRequest({ ...BLANK, name: "x", amount: "300" }, "ZAR", RATE)
      .contribution_amount,
    "16.44"
  )
})

test("the body sends the resolved currency, never the raw URL value", () => {
  const search = { ...BLANK, name: "x", currency: "XYZ", amount: "20" }
  const currency = resolveCreateCurrency(search.currency, ["ZAR"])
  assert.equal(createStokvelRequest(search, currency, "1").currency, "ZAR")
})

test("typing a name on a fresh wizard stays on the name step", () => {
  // /app/stokvels/new has no ?step until Continue is pressed.
  assert.equal(resolveCreateStep({ ...BLANK, name: "S" }, true, false), "name")
  assert.equal(
    resolveCreateStep({ ...BLANK, name: "Savings club" }, true, false),
    "name"
  )
  // Continue still moves on.
  assert.equal(
    resolveCreateStep({ ...BLANK, name: "S", step: "amount" }, true, false),
    "amount"
  )
})
