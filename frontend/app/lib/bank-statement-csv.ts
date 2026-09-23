/** Bank-statement file the deposit reconciliation job reads.
 *
 * Columns match `api/scripts/sample_bank_statement.csv`. The API only uses
 * reference, amount, and date; description is for the person reconciling.
 */

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

/** The demo file checked in next to the API, so a walkthrough can download
 * the same lines the sample script uses. */
export const SAMPLE_STATEMENT_LINES: readonly StatementLine[] = [
  {
    date: "2026-09-08",
    description: "EFT Received",
    reference: "sian1-zar",
    amount: "1500.00",
  },
  {
    date: "2026-09-08",
    description: "POS Refund",
    reference: "thabo2-zar",
    amount: "250.50",
  },
  {
    date: "2026-09-08",
    description: "Salary Payment - Sept",
    reference: "SALARY-SEP26",
    amount: "-18500.00",
  },
  {
    date: "2026-09-09",
    description: "EFT Received",
    reference: "remitx deposit",
    amount: "800.00",
  },
  {
    date: "2026-09-09",
    description: "Office Rent",
    reference: "RENT-CBD-092026",
    amount: "-12000.00",
  },
  {
    date: "2026-09-09",
    description: "EFT Received",
    reference: "amahle1-zar",
    amount: "3200.00",
  },
  {
    date: "2026-09-09",
    description: "Card Payment - AWS",
    reference: "AWS-INV-88213",
    amount: "-640.75",
  },
  {
    date: "2026-09-10",
    description: "EFT Received",
    reference: "kagiso1-zr",
    amount: "500.00",
  },
  {
    date: "2026-09-10",
    description: "EFT Received",
    reference: "sian1-tok",
    amount: "4000.00",
  },
  {
    date: "2026-09-10",
    description: "Bank Charges",
    reference: "BANK-FEES-SEP",
    amount: "-45.00",
  },
  {
    date: "2026-09-10",
    description: "EFT Received",
    reference: "",
    amount: "900.00",
  },
  {
    date: "2026-09-10",
    description: "EFT Received",
    reference: "thabo2-zar",
    amount: "100.00",
  },
]

export function missingStatementColumns(headers: readonly string[]): string[] {
  return REQUIRED_STATEMENT_COLUMNS.filter(
    (column) => !headers.includes(column)
  )
}

function escapeCell(value: string): string {
  if (/[",\r\n]/.test(value)) {
    return `"${value.replaceAll('"', '""')}"`
  }
  return value
}

export function statementToCsv(lines: readonly StatementLine[]): string {
  const header = STATEMENT_COLUMNS.join(",")
  const body = lines.map((line) =>
    STATEMENT_COLUMNS.map((column) => escapeCell(line[column])).join(",")
  )
  return [header, ...body].join("\n") + (lines.length > 0 ? "\n" : "")
}

/** RFC-style records so a description that contains a comma still round-trips
 * into the process-deposits uploader. Blank lines are dropped. */
export function parseStatementCsv(text: string): {
  headers: string[]
  rows: CsvRow[]
} {
  const records = parseRecords(text).filter((record) =>
    record.some((cell) => cell.length > 0)
  )
  if (records.length === 0) return { headers: [], rows: [] }

  const headers = records[0].map((cell) => cell.trim())
  const rows = records.slice(1).map((record) => {
    const row: CsvRow = {}
    headers.forEach((header, index) => {
      row[header] = (record[index] ?? "").trim()
    })
    return row
  })
  return { headers, rows }
}

function parseRecords(text: string): string[][] {
  const records: string[][] = []
  let row: string[] = []
  let cell = ""
  let inQuotes = false

  const pushCell = () => {
    row.push(cell.trim())
    cell = ""
  }

  const pushRow = () => {
    records.push(row)
    row = []
  }

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (inQuotes) {
      if (char === '"') {
        if (text[index + 1] === '"') {
          cell += '"'
          index += 1
        } else {
          inQuotes = false
        }
      } else {
        cell += char
      }
      continue
    }

    if (char === '"') {
      inQuotes = true
      continue
    }
    if (char === ",") {
      pushCell()
      continue
    }
    if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") index += 1
      pushCell()
      pushRow()
      continue
    }
    cell += char
  }

  if (cell.length > 0 || row.length > 0) {
    pushCell()
    pushRow()
  }

  return records
}
