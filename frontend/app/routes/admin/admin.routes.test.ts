import { assert, test } from "vitest"

import {
  ADMIN_ROUTE_INDEX,
  adminRouteContext,
  getFlattenedAdminRoutes,
} from "./admin.routes.ts"

test("adminRouteContext ignores missing module keys", () => {
  assert.equal(adminRouteContext(""), undefined)
  assert.equal(adminRouteContext(undefined as unknown as string), undefined)
})

test("every registered admin route resolves title and parent group", () => {
  for (const route of getFlattenedAdminRoutes()) {
    const context = adminRouteContext(route.module)
    assert.ok(context?.title, route.module)
    assert.notEqual(context?.title, "IAM")
  }
})

test("nav group labels without routes are not page titles", () => {
  const groupOnly = ADMIN_ROUTE_INDEX.filter((node) => !node.route)
  for (const group of groupOnly) {
    assert.equal(adminRouteContext(group.label), undefined)
  }
})
