import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import { shopFixture } from "./__fixtures__/fixtures.ts"
import { affected, diffApi, diffDatabase, impactReport } from "./impact.ts"
import { ingestDbml } from "./load/dbml.ts"
import { buildGraph } from "./load/graph.ts"
import { ingestOpenApi } from "./load/openapi.ts"
import { nodeKey } from "./model.ts"
import { checkReport, counts } from "./report.ts"

const config = shopFixture()
const { graph } = buildGraph(config)
const read = (file: string) =>
  readFileSync(path.join(config.root, file), "utf8")

const JOURNEY = "docs/journeys/checkout.mdx"

describe("diffDatabase", () => {
  const before = graph.database
  const after = ingestDbml(
    read("docs/database/schema.dbml")
      .replace('"status" text [not null', '"state" text [not null')
      .replace(
        '"total" numeric(12,2) [not null',
        '"total" numeric(14,2) [not null'
      )
      .replace('Table "users" {', 'Table "users" {\n  "name" text'),
    "schema.dbml",
    config.ignoredTables
  ).database

  it("reports columns added, removed and changed", () => {
    expect(
      diffDatabase(before, after).map(
        (c) => `${c.kind} ${c.label} ${c.details.join("; ")}`
      )
    ).toEqual([
      "changed orders.total type numeric(12,2) → numeric(14,2)",
      "removed payments.status ",
      "added payments.state text",
      "added users.name text",
    ])
  })

  it("reports nothing when nothing changed", () => {
    expect(diffDatabase(before, before)).toEqual([])
  })
})

describe("diffApi", () => {
  const spec = JSON.parse(read("frontend/openapi.json"))
  spec.paths["/payments"].post.responses["422"] = { description: "Invalid." }
  spec.components.schemas.PaymentRead.properties.state = { type: "string" }
  spec.paths["/refunds"] = {
    post: { operationId: "create_refund", tags: ["payments"], responses: {} },
  }
  delete spec.paths["/health"]
  const after = ingestOpenApi(spec, "openapi.json").api

  it("reports operations added, removed and changed, schemas included", () => {
    expect(
      diffApi(graph.api, after).map(
        (c) => `${c.kind} ${c.label} ${c.details.join("; ")}`
      )
    ).toEqual([
      "changed POST /payments responses; schema PaymentRead",
      "added POST /refunds ",
      "removed GET /health ",
    ])
  })
})

describe("affected", () => {
  it("follows a column back to the steps, pages, operations and screens that use it", () => {
    expect(affected(graph, nodeKey("column", "payments.status"))).toEqual({
      steps: [nodeKey("step", `${JOURNEY}#payment`)],
      docs: [nodeKey("doc", "docs/concepts/billing.mdx")],
      operations: [nodeKey("operation", "create_payment")],
      components: [
        nodeKey(
          "component",
          "frontend/app/components/payment-screen.tsx#PaymentScreen"
        ),
      ],
    })
  })

  it("reaches a column through its table, but not through its siblings", () => {
    const step = (name: string) => nodeKey("step", `x.mdx#${name}`)
    const location = { file: "x.mdx" }
    const synthetic = {
      ...graph,
      links: [
        {
          kind: "touches" as const,
          from: step("a"),
          to: nodeKey("column", "orders.total"),
          location,
        },
        {
          kind: "touches" as const,
          from: step("b"),
          to: nodeKey("table", "orders"),
          location,
        },
        {
          kind: "touches" as const,
          from: step("c"),
          to: nodeKey("column", "orders.user_id"),
          location,
        },
      ],
    }
    expect(
      affected(synthetic, nodeKey("column", "orders.user_id")).steps
    ).toEqual([step("b"), step("c")])
    // A change to the table as a whole reaches all three.
    expect(affected(synthetic, nodeKey("table", "orders")).steps).toHaveLength(
      3
    )
  })

  it("reports what an impact touches, in Markdown for a PR", () => {
    const report = impactReport(
      graph,
      {
        api: [],
        database: [
          {
            kind: "changed",
            target: nodeKey("column", "payments.status"),
            label: "payments.status",
            details: ["type text → payment_status"],
          },
        ],
      },
      "origin/main",
      "markdown"
    )
    expect(report).toBe(`## Docs impact against \`origin/main\`

### Database

- \`payments.status\` changed: type text → payment_status
  - 🧭 Checkout › Payment
  - 📄 Billing
  - 🔌 POST /payments
  - 🖥 PaymentScreen
`)
  })
})

describe("checkReport", () => {
  it("lists every resolved reference and every problem, page by page", () => {
    const report = checkReport(graph, "text")
    expect(report).toContain("Checkout  (docs/journeys/checkout.mdx)")
    expect(report).toContain(
      "  ✓ Payment calls POST /payments (payments.createPayment)"
    )
    expect(report).toContain(
      "  ✓ POST /payments (payments.createPayment) uses payments"
    )
    expect(report).toContain("  ✓ Checkout branches to Confirmation (Yes)")
    expect(report).toMatch(
      / {2}⚠ \d+:3 OrderConfirmation .* \[component-without-stories\]/
    )
    expect(report).toContain(
      "✓ docs/database/schema.dbml: 3 tables, 2 foreign keys resolve"
    )
    expect(report.trim().endsWith("0 errors, 1 warning")).toBe(true)
    expect(counts(graph)).toEqual({ errors: 0, warnings: 1 })
  })
})
