/** Bank-statement file the deposit reconciliation job reads.
 *
 * Columns match `api/scripts/sample_bank_statement.csv`. The API only uses
 * reference, amount, and date; description is for the person reconciling.
 */

import { parse, stringify } from "csv/sync"

export const STATEMENT_COLUMNS = [
  "date",
  "description",
  "reference",
  "amount",
] as const

export type StatementColumn = (typeof STATEMENT_COLUMNS)[number]

export type StatementLine = Record<StatementColumn, string>

export type CsvRow = Record<string, string>

/** What `process_deposits` refuses to run without. */
export const REQUIRED_STATEMENT_COLUMNS = ["reference", "amount"] as const

export function missingStatementColumns(headers: readonly string[]): string[] {
  return REQUIRED_STATEMENT_COLUMNS.filter(
    (column) => !headers.includes(column)
  )
}

export function statementToCsv(lines: readonly StatementLine[]): string {
  return stringify([...lines], {
    header: true,
    columns: [...STATEMENT_COLUMNS],
  })
}

export function parseStatementCsv(text: string): {
  headers: string[]
  rows: CsvRow[]
} {
  const rows = parse(text, {
    columns: true,
    skip_empty_lines: true,
    trim: true,
    relax_column_count: true,
  }) as CsvRow[]

  if (rows.length === 0) return { headers: [], rows: [] }

  return { headers: Object.keys(rows[0]), rows }
}
