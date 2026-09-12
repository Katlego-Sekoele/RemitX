import * as PhosphorIcons from "@phosphor-icons/react"

import type { PhosphorIconName } from "~/lib/phosphor-icon-name"
import { ADMIN_ROUTE_INDEX } from "~/routes/admin/admin.routes"

export type AdminNavItem = {
  title: string
  href: string
  order: number
}

export type AdminNavGroup = {
  id: string
  label: string
  order: number
  icon: PhosphorIcons.Icon | undefined
  items: AdminNavItem[] | undefined
}

function hrefForPath(path: string): string {
  return `/${path}`
}

function slugify(label: string): string {
  return label.toLowerCase().replace(/\s+/g, "-")
}

/** Nav groups derived from ``ADMIN_ROUTE_INDEX`` nodes that have child items. */
export function discoverAdminNav(): AdminNavGroup[] {
  return ADMIN_ROUTE_INDEX.filter(
    (node) => (node.childItems?.length ?? 0) > 0 && node.icon != null
  )
    .map((group) => ({
      id: slugify(group.label),
      label: group.label,
      order: group.order ?? 0,
      icon: group.icon && PhosphorIcons[group.icon],
      items:
        group.childItems &&
        group.childItems
          .filter((item) => item.route != null)
          .map((item) => ({
            title: item.label,
            href: hrefForPath(item.route!.path),
            order: item.order ?? 0,
          }))
          .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title)),
    }))
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))
}
