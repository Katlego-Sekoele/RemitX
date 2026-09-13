import { useState } from "react"

import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { ApplicationReview } from "~/components/admin/kyc-review/application-review"
import { useHasPermission } from "~/hooks/use-permissions"
import { PERMISSIONS } from "~/lib/permissions"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/application-review"

// The literal path, not `import.meta.filename` — see routes/admin/access.tsx.
const ROUTE_MODULE = "routes/admin/kyc/application-review.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/** Gated like the queue: the API requires `kyc:application:read` to read an
 * application, and each action checks its own permission. */
export default function KycApplicationReviewPage({
  params,
}: Route.ComponentProps) {
  const canRead = useHasPermission(PERMISSIONS.kycApplicationRead)
  const [applicantName, setApplicantName] = useState<string | null>(null)

  if (!canRead) return <ForbiddenPage />

  return (
    <AdminPageFrame module={ROUTE_MODULE} title={applicantName ?? undefined}>
      <ApplicationReview
        key={params.applicationId}
        applicationId={params.applicationId}
        onApplicantName={setApplicantName}
      />
    </AdminPageFrame>
  )
}
