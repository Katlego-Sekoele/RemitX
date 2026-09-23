/** Customer dashboard routes, nav, and page titles — same idea as admin. */

import type { PhosphorIconName } from "~/lib/phosphor-icon-name"

type AppRoute = {
  path: string
  module: string
}

export type AppSubNavItem = {
  path: string
  label: string
  icon?: PhosphorIconName
  /** Active only on this exact path, not on paths beneath it. */
  exact?: boolean
  /** Show an attention badge on this item while KYC is not approved. */
  kycAttention?: boolean
}

export type AppRouteIndex = {
  route: AppRoute
  label: string
  order?: number
  icon?: PhosphorIconName
  /** Show an attention badge on this item while KYC is not approved. */
  kycAttention?: boolean
  /** Sections of the page, listed beneath it in the sidebar. */
  children?: readonly AppSubNavItem[]
}

// Profile is Clerk's <UserProfile> with its own navbar hidden; these drive it
// by path instead (see routes/app/profile.tsx). Each `path` must match the
// page's `url` there, or Clerk's default page path for account and security.
export const PROFILE_SECTIONS: readonly AppSubNavItem[] = [
  {
    path: "app/profile",
    label: "Account",
    icon: "UserCircleIcon",
    exact: true,
  },
  { path: "app/profile/contact", label: "Contact", icon: "PhoneIcon" },
  {
    // An application and its wizard live beneath this path too, and keep
    // this item active.
    path: "app/profile/verification",
    label: "Verification",
    icon: "IdentificationBadgeIcon",
    kycAttention: true,
  },
  { path: "app/profile/security", label: "Security", icon: "ShieldCheckIcon" },
]

export const APP_ROUTE_INDEX: readonly AppRouteIndex[] = [
  {
    route: { path: "app", module: "routes/app/index.tsx" },
    label: "Overview",
    order: 0,
    icon: "HouseIcon",
  },
  {
    route: { path: "app/accounts", module: "routes/app/accounts.tsx" },
    label: "Accounts",
    order: 10,
    icon: "WalletIcon",
  },
  {
    route: { path: "app/send", module: "routes/app/send.tsx" },
    label: "Send",
    order: 15,
    icon: "PaperPlaneTiltIcon",
    kycAttention: true,
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
    kycAttention: true,
    children: PROFILE_SECTIONS,
  },
]

export function getFlattenedAppRoutes(
  additionalManualRoutes: AppRoute[] = []
): AppRoute[] {
  // A manual route replaces the index's route for the same module rather than
  // duplicating it (route ids are module paths) — e.g. Profile's splat, which
  // Clerk's path routing needs and which matches the bare path too. A Set of
  // route objects would not dedupe: each object is distinct.
  const manualModules = new Set(
    additionalManualRoutes.map((route) => route.module)
  )
  return [
    ...APP_ROUTE_INDEX.map((node) => node.route).filter(
      (route) => !manualModules.has(route.module)
    ),
    ...additionalManualRoutes,
  ]
}

export type AppRouteContext = {
  title: string
}

export function appRouteContext(module: string): AppRouteContext | undefined {
  const match = APP_ROUTE_INDEX.find((node) => node.route.module === module)
  return match ? { title: match.label } : undefined
}
