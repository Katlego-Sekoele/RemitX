import { MagnifyingGlassIcon, ShieldCheckIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useSearchParams } from "react-router"

import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import {
  DocumentKindIcon,
  KycDocumentViewer,
} from "~/components/admin/kyc-document-viewer"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { Input } from "~/components/ui/input"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { useHasPermission } from "~/hooks/use-permissions"
import type { KycDocument } from "~/lib/api"
import { PERMISSIONS } from "~/lib/permissions"
import { useApi } from "~/lib/use-api"
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

/** The query parameter the application detail page (#20) will link in with. */
const APPLICATION_PARAM = "application"

function formatSize(bytes: number) {
  const kilobytes = bytes / 1024
  return kilobytes < 1024
    ? `${Math.round(kilobytes)} KB`
    : `${(kilobytes / 1024).toFixed(1)} MB`
}

function formatDate(value: string | null) {
  if (!value) return "—"
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

/** The document type as a label, without inventing a second vocabulary: the
 * API's values are snake_case members of one enum. */
function formatType(documentType: string) {
  const words = documentType.replace(/_/g, " ")
  return words.charAt(0).toUpperCase() + words.slice(1)
}

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
  const api = useApi()
  const [searchParams, setSearchParams] = useSearchParams()
  const applicationId = searchParams.get(APPLICATION_PARAM) ?? ""
  const [draft, setDraft] = useState(applicationId)
  const [selected, setSelected] = useState<KycDocument | null>(null)

  const documents = useQuery({
    queryKey: ["kyc-documents", applicationId],
    queryFn: () => api.listApplicationDocuments(applicationId),
    enabled: applicationId.length > 0,
  })

  function loadApplication(event: React.FormEvent) {
    event.preventDefault()
    setSelected(null)
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
        <p className="max-w-xl text-sm text-muted-foreground">
          Evidence uploaded against a KYC application. Opening one issues a link
          that expires in five minutes and records who looked, in the audit log.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Application</CardTitle>
          <CardDescription>
            Paste the application id from the review queue.
          </CardDescription>
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

      {applicationId.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Documents</CardTitle>
            <CardDescription>
              Only verified uploads appear here. An upload that was never
              completed stays pending and is never shown for review.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {documents.isPending ? (
              <Skeleton className="h-32 w-full" />
            ) : documents.isError ? (
              <Alert variant="destructive">
                <AlertTitle>Could not load documents</AlertTitle>
                <AlertDescription>
                  {documents.error instanceof Error
                    ? documents.error.message
                    : "Something went wrong."}
                </AlertDescription>
              </Alert>
            ) : documents.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No verified documents on this application yet.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Size</TableHead>
                    <TableHead>Uploaded</TableHead>
                    <TableHead>SHA-256</TableHead>
                    <TableHead className="text-right">View</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documents.data.map((document) => (
                    <TableRow key={document.document_id}>
                      <TableCell className="flex items-center gap-2">
                        <DocumentKindIcon contentType={document.content_type} />
                        {formatType(document.document_type)}
                      </TableCell>
                      <TableCell>{formatSize(document.size_bytes)}</TableCell>
                      <TableCell>{formatDate(document.stored_at)}</TableCell>
                      <TableCell>
                        {/* Enough of the digest to compare two rows by eye;
                            the whole value is in the API response. */}
                        <Badge
                          variant="secondary"
                          className="font-mono text-[11px]"
                        >
                          {document.sha256?.slice(0, 12) ?? "—"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelected(document)}
                        >
                          Open
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}

            {selected && (
              <div className="flex flex-col gap-2">
                <Alert>
                  <ShieldCheckIcon data-icon="inline-start" />
                  <AlertTitle>
                    {formatType(selected.document_type)} — sandboxed preview
                  </AlertTitle>
                  <AlertDescription>
                    Rendered without scripts and without access to this page. An
                    uploaded file is untrusted input from a stranger.
                  </AlertDescription>
                </Alert>
                <KycDocumentViewer document={selected} />
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </AdminPageFrame>
  )
}
