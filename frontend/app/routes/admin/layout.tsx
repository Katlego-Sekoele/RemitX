import { lazy, Suspense } from "react"

import { AdminLayoutSkeleton } from "~/components/admin/admin-layout-skeleton"

const AdminLayoutInner = lazy(async () => {
  const module = await import("~/components/admin/admin-layout-inner")
  return { default: module.AdminLayoutInner }
})

/**
 * Admin routes are lazy-loaded so customers never download the staff bundle.
 * Bundle size, not security — the server still enforces permissions on every
 * request.
 */
export default function AdminLayout() {
  return (
    <Suspense fallback={<AdminLayoutSkeleton />}>
      <AdminLayoutInner />
    </Suspense>
  )
}
