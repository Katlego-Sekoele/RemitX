import vm from "node:vm"
import { assert, test } from "vitest"
import { build } from "vite"

// Process deposits lazy-loads this module in the browser. The Node `csv/sync`
// entry touches `Buffer` while the chunk evaluates, and React Router reloads
// the page instead of opening the route.
test("statement csv evaluates in a browser without Node Buffer", async () => {
  const result = await build({
    configFile: false,
    logLevel: "error",
    resolve: { tsconfigPaths: true },
    build: {
      write: false,
      minify: false,
      lib: {
        entry: "app/lib/bank-statement-csv.ts",
        formats: ["iife"],
        name: "statementCsv",
        fileName: "statement",
      },
    },
  })
  const output = Array.isArray(result) ? result[0] : result
  const chunk = output.output.find((file) => file.type === "chunk")
  if (!chunk || chunk.type !== "chunk") {
    throw new Error("expected a client chunk")
  }

  const sandbox: {
    statementCsv?: {
      parseStatementCsv: (text: string) => {
        rows: { description: string }[]
      }
      statementToCsv: (
        lines: {
          date: string
          description: string
          reference: string
          amount: string
          currency: string
        }[]
      ) => string
    }
  } = {}

  vm.runInNewContext(chunk.code, sandbox)

  const csv = sandbox.statementCsv!.statementToCsv([
    {
      date: "2026-09-11",
      description: 'EFT Received, "salary"',
      reference: "sipho1-zar",
      amount: "42.00",
      currency: "ZAR",
    },
  ])
  const parsed = sandbox.statementCsv!.parseStatementCsv(csv)

  assert.equal(parsed.rows[0].description, 'EFT Received, "salary"')
})
