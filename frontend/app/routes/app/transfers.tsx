import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { RecentTransfers } from "~/components/transfers/recent-transfers"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import type { Route } from "./+types/transfers"

const ROUTE_MODULE = "routes/app/transfers.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Transfers — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function TransfersPage() {
  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>Transfers</PageHeaderTitle>
          <PageHeaderDescription>
            Money you&apos;ve sent and received, newest first.
          </PageHeaderDescription>
        </PageHeader>
        <RecentTransfers />
      </div>
    </AppPageFrame>
  )
}
