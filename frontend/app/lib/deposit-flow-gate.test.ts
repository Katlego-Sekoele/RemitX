import assert from "node:assert/strict"
import test from "node:test"

import { ADMIN_ROUTE_INDEX } from "../routes/admin/admin.routes.ts"

type RouteNode = {
  label: string
  permission?: string
  route?: { path: string }
  childItems?: RouteNode[]
}

function routedNodes(nodes: readonly RouteNode[]): RouteNode[] {
  return nodes.flatMap((node) => [
    ...(node.route ? [node] : []),
    ...routedNodes(node.childItems ?? []),
  ])
}

test("every deposit-processing page requires cash-in read", () => {
  const deposits = ADMIN_ROUTE_INDEX.find((node) => node.label === "Deposits")
  assert.ok(deposits)

  const pages = routedNodes(deposits.childItems ?? [])
  const paths = pages.map((page) => page.route?.path)

  assert.deepEqual(paths.sort(), [
    "admin/process-deposits",
    "admin/statement-csv",
  ])
  for (const page of pages) {
    assert.equal(page.permission, "cashin:read")
  }
})
