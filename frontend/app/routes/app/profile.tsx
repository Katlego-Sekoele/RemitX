import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import type { Route } from "./+types/profile"
import { PageHeader, PageHeaderTitle } from "~/components/ui/page-header"

const ROUTE_MODULE = "routes/app/profile.tsx"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Profile — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function ProfilePage() {
  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <PageHeader>
        <PageHeaderTitle>Profile</PageHeaderTitle>
      </PageHeader>
    </AppPageFrame>
  )
}
