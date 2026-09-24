import { assert, test } from "vitest"

import {
  APP_ROUTE_INDEX,
  appRouteContext,
  getFlattenedAppRoutes,
} from "./app.routes.ts"

/** Same manual routes `routes.ts` passes into `getFlattenedAppRoutes`. */
const MANUAL_APP_ROUTES = [
  { path: "app/profile/*", module: "routes/app/profile.tsx" },
  {
    path: "app/accounts/:accountId",
    module: "routes/app/account-history.tsx",
  },
]

test("appRouteContext ignores missing module keys", () => {
  assert.equal(appRouteContext(""), undefined)
  assert.equal(appRouteContext(undefined as unknown as string), undefined)
})

test("every sidebar app route resolves a title from the registry", () => {
  for (const node of APP_ROUTE_INDEX) {
    const context = appRouteContext(node.route.module)
    assert.equal(context?.title, node.label, node.route.module)
  }
})

test("flattened app routes are either in the registry or nested with overrides", () => {
  const registered = new Set(APP_ROUTE_INDEX.map((node) => node.route.module))
  const nestedWithoutRegistry = new Set([
    "routes/app/account-history.tsx",
    "routes/app/transfer.tsx",
  ])

  for (const route of getFlattenedAppRoutes(MANUAL_APP_ROUTES)) {
    if (registered.has(route.module)) continue
    assert.ok(
      nestedWithoutRegistry.has(route.module),
      `unexpected app route module: ${route.module}`
    )
  }
})
