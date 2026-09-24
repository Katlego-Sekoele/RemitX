import sampleBankStatementCsv from "../../../../api/scripts/sample_bank_statement.csv?raw"

import { parseStatementCsv, type StatementLine } from "./bank-statement-csv"

/** Demo lines from `api/scripts/sample_bank_statement.csv`. */
export const SAMPLE_STATEMENT_LINES: readonly StatementLine[] =
  parseStatementCsv(sampleBankStatementCsv).rows as StatementLine[]
