import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import type { Route } from "./+types/index"

const ROUTE_MODULE = "routes/admin/index.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Staff portal — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function AdminHome() {
  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          Staff portal
        </h1>
        <p className="max-w-xl text-sm text-muted-foreground">
          Operational tools live here. Use IAM → My roles to review your current
          access.
        </p>
      </div>
    </AdminPageFrame>
  )
}
