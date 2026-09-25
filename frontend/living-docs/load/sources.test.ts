import { describe, expect, it } from "vitest"

import { canonicalizeDbml, ingestDbml } from "./dbml.ts"
import { ingestOpenApi } from "./openapi.ts"

describe("ingestOpenApi", () => {
  const spec = {
    security: [{ Session: [] }],
    paths: {
      "/orders/{order_id}": {
        parameters: [
          { name: "order_id", in: "path", schema: { type: "string" } },
        ],
        get: {
          operationId: "get_order",
          tags: ["orders"],
          parameters: [
            { name: "expand", in: "query", schema: { type: "boolean" } },
          ],
          responses: {
            "404": { description: "Not found." },
            "200": {
              description: "The order.",
              content: {
                "application/json": {
                  schema: { $ref: "#/components/schemas/Order" },
                },
              },
            },
          },
        },
        delete: { tags: ["orders"], responses: {} },
      },
      "/health": {
        get: {
          operationId: "health",
          tags: ["system"],
          security: [],
          responses: {},
        },
      },
    },
  }
  const { api, diagnostics } = ingestOpenApi(spec, "openapi.json")

  it("merges path and operation parameters, a path parameter being required", () => {
    expect(api.operations.get_order.parameters).toEqual([
      {
        name: "order_id",
        in: "path",
        required: true,
        description: undefined,
        schema: { type: "string" },
      },
      {
        name: "expand",
        in: "query",
        required: false,
        description: undefined,
        schema: { type: "boolean" },
      },
    ])
  })

  it("takes the spec's security unless the operation overrides it", () => {
    expect(api.operations.get_order.auth).toEqual(["Session"])
    expect(api.operations.health.auth).toEqual([])
  })

  it("orders responses by status and keeps their schemas", () => {
    expect(
      api.operations.get_order.responses.map((r) => [r.status, r.schema])
    ).toEqual([
      ["200", { $ref: "#/components/schemas/Order" }],
      ["404", undefined],
    ])
  })

  it("reports an operation nothing could reference", () => {
    expect(diagnostics).toEqual([
      expect.objectContaining({
        code: "operation-without-id",
        message: expect.stringContaining("DELETE /orders/{order_id}"),
      }),
    ])
  })
})

describe("ingestDbml", () => {
  const source = `
Table "users" {
  "id" uuid [pk, not null]
}

Table "profiles" {
  "user_id" uuid [pk, not null]
  "bio" text [default: 'hi', check: \`length(bio) < 500\`]
}

Table "orders" {
  "id" uuid [pk, not null]
  "user_id" uuid [not null]
  "reviewer_id" uuid
}

Table "alembic_version" {
  "version_num" varchar(32) [pk, not null]
}

Ref "orders_user_id_fkey":"users"."id" < "orders"."user_id" [delete: cascade]

Ref "profiles_user_id_fkey":"users"."id" - "profiles"."user_id"

Ref "orders_reviewer_id_fkey":"orders"."reviewer_id" > "users"."id"
`
  const { database } = ingestDbml(source, "schema.dbml", ["alembic_version"])

  it("reads columns, defaults and checks", () => {
    expect(Object.keys(database.tables)).toEqual([
      "users",
      "profiles",
      "orders",
    ])
    expect(database.tables.profiles.columns[1]).toMatchObject({
      name: "bio",
      type: "text",
      notNull: false,
      default: "hi",
      checks: [{ expression: "length(bio) < 500" }],
    })
  })

  it("points each foreign key from its holder to what it references", () => {
    expect(
      database.relationships.map(
        (r) => `${r.name}: ${r.from.table} → ${r.to.table}`
      )
    ).toEqual([
      "orders_user_id_fkey: orders → users",
      // One-to-one: db2dbml writes the referenced table first.
      "profiles_user_id_fkey: profiles → users",
      "orders_reviewer_id_fkey: orders → users",
    ])
    expect(database.relationships[0].onDelete).toBe("cascade")
  })

  it("reports DBML it cannot parse, where it fails", () => {
    const { database: empty, diagnostics } = ingestDbml(
      'Table "a" {\n  "id" uuid [pk\n}\n',
      "schema.dbml"
    )
    expect(empty.tables).toEqual({})
    expect(diagnostics[0]).toMatchObject({
      code: "invalid-dbml",
      location: { file: "schema.dbml", line: expect.any(Number) },
    })
  })
})

describe("canonicalizeDbml", () => {
  const table = (checks: string[]) => `Table "accounts" {
  "id" uuid [pk, not null]
  "balance" numeric [not null]

  Checks {
${checks.join("\n")}
  }
}
`
  const b = "    `balance >= 0` [name: 'b_nonneg']"
  const a = "    `id IS NOT NULL` [name: 'a_id']"

  it("orders what db2dbml leaves unordered, and nothing else", () => {
    const one = canonicalizeDbml(table([b, a]))
    const two = canonicalizeDbml(table([a, b]))
    expect(one).toBe(two)
    expect(one.indexOf("a_id")).toBeLessThan(one.indexOf("b_nonneg"))
    // Already canonical output comes back byte for byte.
    expect(canonicalizeDbml(one)).toBe(one)
  })
})
