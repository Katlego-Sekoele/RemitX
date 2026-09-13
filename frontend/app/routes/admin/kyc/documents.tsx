import { MagnifyingGlassIcon } from "@phosphor-icons/react"
import { useState } from "react"
import { useSearchParams } from "react-router"

import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { KycApplicationDocuments } from "~/components/admin/kyc-application-documents"
import { Button } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Input } from "~/components/ui/input"
import { useHasPermission } from "~/hooks/use-permissions"
import { PERMISSIONS } from "~/lib/permissions"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/documents"

const moduleName = import.meta.filename
const pageRoutingContextByModuleName = adminRouteContext(moduleName)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContextByModuleName?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/** Deep link from the review queue (`?application=`). */
const APPLICATION_PARAM = "application"

/**
 * Gated on `kyc:document:read`, the same permission the API requires
 * (routes/admin/kyc_documents.py). Looking at somebody's identity document is
 * its own capability rather than a side effect of being an admin, and the
 * server is what enforces that — this only keeps the UI from offering what it
 * would refuse.
 */
export default function KycDocuments() {
  const canRead = useHasPermission(PERMISSIONS.kycDocumentRead)

  if (!canRead) return <ForbiddenPage />

  return <KycDocumentsPage />
}

function KycDocumentsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const applicationId = searchParams.get(APPLICATION_PARAM) ?? ""
  const [draft, setDraft] = useState(applicationId)

  function loadApplication(event: React.FormEvent) {
    event.preventDefault()
    setSearchParams(draft.trim() ? { [APPLICATION_PARAM]: draft.trim() } : {}, {
      replace: true,
    })
  }

  return (
    <AdminPageFrame module={moduleName}>
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          {pageRoutingContextByModuleName?.title}
        </h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Application</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex gap-2" onSubmit={loadApplication}>
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              aria-label="Application id"
              className="max-w-md font-mono text-xs"
            />
            <Button type="submit">
              <MagnifyingGlassIcon data-icon="inline-start" />
              Load
            </Button>
          </form>
        </CardContent>
      </Card>

      {applicationId.length > 0 ? (
        <KycApplicationDocuments applicationId={applicationId} />
      ) : null}
    </AdminPageFrame>
  )
}
