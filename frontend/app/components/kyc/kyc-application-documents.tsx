import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import {
  DocumentKindIcon,
  KycDocumentViewer,
  type DocumentAudience,
} from "~/components/kyc/kyc-document-viewer"
import { api } from "~/client"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import type { KycDocumentRead as KycDocument } from "~/client"

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

function formatType(documentType: string) {
  const words = documentType.replace(/_/g, " ")
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Evidence for one application. Opening a file issues a short-lived, audited
 * URL — the viewer fetches it itself. Staff read through the admin routes,
 * the applicant through their own; `canRead` is the staff permission gate. */
export function KycApplicationDocuments({
  applicationId,
  audience,
  canRead = true,
}: {
  applicationId: string
  audience: DocumentAudience
  canRead?: boolean
}) {
  const [selected, setSelected] = useState<KycDocument | null>(null)

  useEffect(() => {
    setSelected(null)
  }, [applicationId])

  const query = { query: { application_id: applicationId } }
  const documents = useQuery({
    ...(audience === "staff"
      ? api.admin.kyc.documents.listApplicationDocuments(query)
      : api.kyc.documents.listMyDocuments(query)),
    enabled: canRead && applicationId.length > 0,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Documents</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!canRead ? (
          <p className="text-sm text-muted-foreground">
            You don&apos;t have access to documents.
          </p>
        ) : documents.isPending ? (
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
          <p className="text-sm text-muted-foreground">No documents yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="text-right">View</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.data.map((document) => (
                <TableRow
                  key={document.document_id}
                  data-state={
                    selected?.document_id === document.document_id
                      ? "selected"
                      : undefined
                  }
                >
                  <TableCell className="flex items-center gap-2">
                    <DocumentKindIcon contentType={document.content_type} />
                    {formatType(document.document_type)}
                  </TableCell>
                  <TableCell>{formatSize(document.size_bytes)}</TableCell>
                  <TableCell>{formatDate(document.stored_at)}</TableCell>
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

        {selected ? (
          <KycDocumentViewer
            key={selected.document_id}
            document={selected}
            audience={audience}
          />
        ) : null}
      </CardContent>
    </Card>
  )
}
