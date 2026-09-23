import fs from "node:fs"
import { assert, test } from "vitest"

import {
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
