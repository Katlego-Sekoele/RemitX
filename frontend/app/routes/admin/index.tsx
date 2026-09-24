import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { OperationsCharts } from "~/components/admin/overview/operations-charts"
import { QueueCards } from "~/components/admin/overview/queue-cards"
import { TreasuryCoverage } from "~/components/admin/overview/treasury-coverage"
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
      <div className="flex flex-col gap-6">
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          Staff portal
        </h1>
        <p className="text-muted-foreground">
          Queues, settlement activity, and treasury coverage for the roles you
          hold.
        </p>
        <QueueCards />
        <OperationsCharts />
        <TreasuryCoverage />
      </div>
    </AdminPageFrame>
  )
}
