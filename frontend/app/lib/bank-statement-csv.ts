/** Bank-statement file the deposit reconciliation job reads.
 *
 * Columns match `api/scripts/sample_bank_statement.csv`. The API uses
 * reference, amount, currency, and date; description is for the person
 * reconciling. Currency is that of the RemitX bank account the money came
 * into, and a line is only credited to an account in that currency.
 */

// `csv/sync` is the Node build. It calls `Buffer` while the module evaluates,
// which throws in the browser and makes React Router reload Process deposits
// instead of opening it. The browser sync build ships its own Buffer.
import { parse, stringify } from "csv/browser/esm/sync"

export const STATEMENT_COLUMNS = [
  "date",
  "description",
  "reference",
  "amount",
  "currency",
] as const

export type StatementColumn = (typeof STATEMENT_COLUMNS)[number]

export type StatementLine = Record<StatementColumn, string>

export type CsvRow = Record<string, string>

/** What `process_deposits` refuses to run without. */
export const REQUIRED_STATEMENT_COLUMNS = [
  "reference",
  "amount",
  "currency",
] as const

export function missingStatementColumns(headers: readonly string[]): string[] {
  return REQUIRED_STATEMENT_COLUMNS.filter(
    (column) => !headers.includes(column)
  )
}

/** The currency of the account a line's reference names, when it is not the
 * line's own currency. The job never credits such a line; it waits for an
 * admin. A reference that names no listed account (a typo, "remitx
 * deposit") is not a mismatch. */
export function mismatchedAccountCurrency(
  line: Pick<StatementLine, "reference" | "currency">,
  accounts: readonly { reference: string; currency: string }[]
): string | null {
  const reference = line.reference.trim()
  const account = accounts.find((item) => item.reference === reference)
  if (!account) return null
  const currency = line.currency.trim().toUpperCase()
  return account.currency === currency ? null : account.currency
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
