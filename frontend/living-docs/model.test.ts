import { storyNameFromExport, toId } from "storybook/internal/csf"
import { describe, expect, it } from "vitest"

import { shopFixture } from "./__fixtures__/fixtures.ts"
import { buildGraph } from "./load/graph.ts"
import {
  clientName,
  exportName,
  operationStoryId,
  resolveDoc,
  resolveOperation,
  resolveTable,
  tableStoryId,
} from "./model.ts"

const { graph } = buildGraph(shopFixture())

describe("names", () => {
  it("turns an operationId into the client's function name", () => {
    expect(clientName("create_quote")).toBe("createQuote")
    expect(clientName("reveal_application_pii")).toBe("revealApplicationPii")
    expect(clientName("health")).toBe("health")
  })

  it("keeps CSF exports valid identifiers", () => {
    expect(exportName("create_quote")).toBe("create_quote")
    expect(exportName("delete")).toBe("_delete")
    expect(exportName("audit.log")).toBe("audit_log")
    expect(exportName("2fa-codes")).toBe("_2fa_codes")
  })

  it("gives pages the ids Storybook derives from their titles", () => {
    expect(
      operationStoryId("admin.kyc.applications", "list_applications")
    ).toBe(
      toId(
        "APIs/admin/kyc/applications",
        storyNameFromExport("list_applications")
      )
    )
    expect(operationStoryId("quotes", "create_quote")).toBe(
      "apis-quotes--create-quote"
    )
    expect(tableStoryId("quotes")).toBe("database-quotes--quotes")
  })
})

describe("resolving references", () => {
  it("finds an operation however the docs spell it", () => {
    for (const ref of [
      "create_payment",
      "createPayment",
      "payments.createPayment",
      "payments.create_payment",
    ]) {
      expect(resolveOperation(graph.api, ref)?.id).toBe("create_payment")
    }
    expect(resolveOperation(graph.api, "orders.createPayment")).toBeUndefined()
    expect(resolveOperation(graph.api, "createPaymnt")).toBeUndefined()
  })

  it("finds a table, or a column in it", () => {
    expect(resolveTable(graph.database, "orders")?.column).toBeUndefined()
    expect(resolveTable(graph.database, "orders.total")?.column?.name).toBe(
      "total"
    )
    expect(resolveTable(graph.database, "orders", "total")?.column?.type).toBe(
      "numeric(12,2)"
    )
    expect(resolveTable(graph.database, "orders.nope")).toBeUndefined()
    expect(resolveTable(graph.database, "alembic_version")).toBeUndefined()
  })

  it("finds a page by title or file name", () => {
    expect(resolveDoc(graph.docs, "Checkout", "journey")?.file).toBe(
      "docs/journeys/checkout.mdx"
    )
    expect(resolveDoc(graph.docs, "checkout", "journey")?.title).toBe(
      "Checkout"
    )
    expect(resolveDoc(graph.docs, "Checkout", "concept")).toBeUndefined()
    expect(resolveDoc(graph.docs, "billing")?.kind).toBe("concept")
  })
})
