import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import {
  SAMPLE_STATEMENT_LINES,
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
  assert.deepEqual(parsed.rows, SAMPLE_STATEMENT_LINES)
  assert.equal(
    statementToCsv(SAMPLE_STATEMENT_LINES),
    raw.endsWith("\n") ? raw : `${raw}\n`
  )
})

test("a comma inside a description survives a download and re-upload", () => {
  const lines = [
    {
      date: "2026-09-11",
      description: 'EFT Received, "salary"',
      reference: "sipho1-zar",
      amount: "42.00",
    },
  ]

  const parsed = parseStatementCsv(statementToCsv(lines))

  assert.deepEqual(parsed.rows, lines)
})

test("an upload without the columns the job reads is rejected", () => {
  assert.deepEqual(missingStatementColumns(["date", "description"]), [
    "reference",
    "amount",
  ])
})
