/** Single registry for admin routes, nav groups, and sidebar items. */

// Type-only, deliberately: react-router builds the route config by loading
// this module through vite-node, which does not apply the `~` alias, so a
// value import here breaks `npm run typecheck`. The permission literals below
// are still checked against the union.
import type { PermissionCode } from "~/lib/permissions"
import type { PhosphorIconName } from "~/lib/phosphor-icon-name"

type AdminRoute = {
  path: string
  module: string
}

type AdminRouteIndex = {
  route?: AdminRoute
  label: string
  order?: number
  icon?: PhosphorIconName
  /**
   * The permission the API requires to read this page. Set it and the page
   * leaves the sidebar for callers who do not hold it, rather than linking
   * them to a 403. The page still guards itself — a sidebar is not a gate.
   */
  permission?: PermissionCode
  childItems?: AdminRouteIndex[]
}

export const ADMIN_ROUTE_INDEX: readonly AdminRouteIndex[] = [
  {
    route: {
      path: "admin",
      module: "routes/admin/index.tsx",
    },
    label: "Overview",
  },
  {
    label: "IAM",
    order: 10,
    icon: "IdentificationCardIcon",
    childItems: [
      {
        route: {
          path: "admin/iam/my-roles",
          module: "routes/admin/iam/my-roles.tsx",
        },
        label: "My roles",
        childItems: [],
      },
      {
        route: {
          path: "admin/access",
          module: "routes/admin/access.tsx",
        },
        label: "Access",
        order: 10,
        permission: "role:read",
        childItems: [],
      },
    ],
  },
  {
    label: "KYC",
    order: 15,
    icon: "IdentificationBadgeIcon",
    childItems: [
      {
        route: {
          path: "admin/kyc/applications",
          module: "routes/admin/kyc/applications.tsx",
        },
        label: "Applications",
        permission: "kyc:application:read",
        // The sidebar lists one level under each group, so pages nested here
        // are routed and breadcrumbed but get no sidebar button.
        childItems: [
          {
            route: {
              path: "admin/kyc/applications/:applicationId",
              module: "routes/admin/kyc/application-review.tsx",
            },
            label: "Review",
            permission: "kyc:application:read",
          },
        ],
      },
      {
        route: {
          path: "admin/kyc/documents",
          module: "routes/admin/kyc/documents.tsx",
        },
        label: "Documents",
        permission: "kyc:document:read",
        childItems: [],
      },
    ],
  },
  {
    label: "Deposits",
    order: 20,
    icon: "BankIcon",
    // The whole cash-in flow — building the demo statement and reconciling
    // it — is the treasury role's. Every page under this group declares
    // `cashin:read`, which is what the API requires to see the queue, so a
    // staff member without it never gets a link. Moving money still needs
    // `cashin:confirm` on the process page and on the API.
    childItems: [
      {
        route: {
          path: "admin/statement-csv",
          module: "routes/admin/statement-csv.tsx",
        },
        label: "Statement CSV",
        order: 0,
        permission: "cashin:read",
        childItems: [],
      },
      {
        route: {
          path: "admin/process-deposits",
          module: "routes/admin/process-deposits.tsx",
        },
        label: "Process deposits",
        order: 10,
        permission: "cashin:read",
        childItems: [],
      },
    ],
  },
  {
    label: "Treasury",
    order: 25,
    icon: "VaultIcon",
    childItems: [
      {
        route: {
          path: "admin/platform-accounts",
          module: "routes/admin/platform-accounts.tsx",
        },
        label: "Platform accounts",
        permission: "platform_account:read",
        childItems: [],
      },
    ],
  },
]

export function getFlattenedAdminRoutes(
  adminRouteNode: readonly AdminRouteIndex[] = ADMIN_ROUTE_INDEX
): AdminRoute[] {
  return adminRouteNode.flatMap((node) => [
    ...(node.route ? [node.route] : []),
    ...getFlattenedAdminRoutes(node.childItems ?? []),
  ])
}

export type AdminRouteBreadcrumb = {
  label: string
  href?: string
}

export type AdminRouteContext = {
  title: string
  parent?: AdminRouteBreadcrumb
}

function breadcrumbForNode(node: AdminRouteIndex): AdminRouteBreadcrumb {
  return {
    label: node.label,
    href: node.route ? `/${node.route.path}` : undefined,
  }
}

function findRouteContextByModule(
  module: string,
  nodes: readonly AdminRouteIndex[] = ADMIN_ROUTE_INDEX,
  parent?: AdminRouteIndex
): AdminRouteContext | undefined {
  if (!module) return undefined

  for (const node of nodes) {
    if (node.route?.module === module) {
      return {
        title: node.label,
        parent: parent ? breadcrumbForNode(parent) : undefined,
      }
    }

    const match = findRouteContextByModule(module, node.childItems ?? [], node)
    if (match) return match
  }

  return undefined
}

/** Title and breadcrumb parent for a registered admin route module. */
export function adminRouteContext(
  module: string
): AdminRouteContext | undefined {
  return findRouteContextByModule(module)
}
