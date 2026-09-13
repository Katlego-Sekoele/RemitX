/** Customer dashboard routes, nav, and page titles — same idea as admin. */

import type { PhosphorIconName } from "~/lib/phosphor-icon-name"

type AppRoute = {
  path: string
  module: string
}

export type AppRouteIndex = {
  route: AppRoute
  label: string
  order?: number
  icon?: PhosphorIconName
  /** Show an attention badge on this item while KYC is not approved. */
  kycAttention?: boolean
  /** Leave this item out of the sidebar once KYC is approved. */
  hideWhenVerified?: boolean
}

export const APP_ROUTE_INDEX: readonly AppRouteIndex[] = [
  {
    route: { path: "app", module: "routes/app/index.tsx" },
    label: "Overview",
    order: 0,
    icon: "HouseIcon",
  },
  {
    // Lives under Profile; surfaced in the sidebar only until it is done.
    route: {
      path: "app/profile/verification",
      module: "routes/app/verification/history.tsx",
    },
    label: "Verification",
    order: 10,
    icon: "IdentificationBadgeIcon",
    kycAttention: true,
    hideWhenVerified: true,
  },
  {
    route: {
      path: "app/beneficiaries",
      module: "routes/app/beneficiaries.tsx",
    },
    label: "Beneficiaries",
    order: 20,
    icon: "UsersThreeIcon",
  },
  {
    route: { path: "app/profile", module: "routes/app/profile.tsx" },
    label: "Profile",
    order: 30,
    icon: "UserIcon",
  },
]

export function getFlattenedAppRoutes(): AppRoute[] {
  return APP_ROUTE_INDEX.filter(
    // Declared with their layouts in routes.ts.
    (node) => !node.route.path.startsWith("app/profile/verification")
  ).map((node) => node.route)
}

export type AppRouteContext = {
  title: string
}

export function appRouteContext(module: string): AppRouteContext | undefined {
  const match = APP_ROUTE_INDEX.find((node) => node.route.module === module)
  return match ? { title: match.label } : undefined
}
