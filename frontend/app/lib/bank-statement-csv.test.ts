import fs from "node:fs"
import { assert, test } from "vitest"

import {
  mismatchedAccountCurrency,
  missingStatementColumns,
  parseStatementCsv,
  statementToCsv,
} from "./bank-statement-csv.ts"

test("the sample file is the statement the page downloads", () => {
  const raw = fs.readFileSync(
    new URL("../../../api/scripts/sample_bank_statement.csv", import.meta.url),
    "utf8"
  )
  const parsed = parseStatementCsv(raw)

  assert.deepEqual(missingStatementColumns(parsed.headers), [])
  assert.equal(statementToCsv(parsed.rows as typeof parsed.rows), raw)
})

test("a comma inside a description survives a download and re-upload", () => {
  const lines = [
    {
      date: "2026-09-11",
      description: 'EFT Received, "salary"',
      reference: "sipho1-zar",
      amount: "42.00",
      currency: "ZAR",
    },
  ]

  const parsed = parseStatementCsv(statementToCsv(lines))

  assert.deepEqual(parsed.rows, lines)
})

test("an upload without the columns the job reads is rejected", () => {
  assert.deepEqual(missingStatementColumns(["date", "description"]), [
    "reference",
    "amount",
    "currency",
  ])
})

test("an upload has to say which currency each line is in", () => {
  assert.deepEqual(
    missingStatementColumns(["date", "description", "reference", "amount"]),
    ["currency"]
  )
})

const accounts = [
  { reference: "sipho1-zar", currency: "ZAR" },
  { reference: "sipho1-usd", currency: "USD" },
]

test("a line in another currency than its account is a mismatch", () => {
  assert.equal(
    mismatchedAccountCurrency(
      { reference: "sipho1-usd", currency: "ZAR" },
      accounts
    ),
    "USD"
  )
  assert.equal(
    mismatchedAccountCurrency(
      { reference: "sipho1-zar", currency: "USD" },
      accounts
    ),
    "ZAR"
  )
})

test("a line in its account's currency is not a mismatch", () => {
  assert.equal(
    mismatchedAccountCurrency(
      { reference: " sipho1-usd ", currency: "usd" },
      accounts
    ),
    null
  )
})

test("a reference that names no account is not a mismatch", () => {
  assert.equal(
    mismatchedAccountCurrency(
      { reference: "remitx deposit", currency: "ZAR" },
      accounts
    ),
    null
  )
})
