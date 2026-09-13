import {
  ArrowSquareOutIcon,
  FileTextIcon,
  ImageIcon,
  WarningIcon,
} from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"

import { api } from "~/client"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import { Skeleton } from "~/components/ui/skeleton"
import type { KycDocumentRead as KycDocument } from "~/client"

/** Ask for a fresh link a little before the five-minute one expires, so a
 * reviewer reading a long document does not watch it go blank. */
const URL_REFRESH_MS = 4 * 60 * 1000

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]

/**
 * Renders one uploaded document from its short-lived, audited URL.
 *
 * Images go in an `<img>`, which cannot run anything. PDFs go in an iframe
 * *without* `sandbox`: Chromium's and Edge's PDF viewers refuse to load in a
 * sandboxed frame. That is safe because the URL is on the storage origin, not
 * this app's, so the same-origin policy already keeps the file away from this
 * page; the upload was also sniffed as a real PDF and is served with that type.
 */
export function KycDocumentViewer({ document }: { document: KycDocument }) {
  const link = useQuery({
    ...api.admin.kyc.documents.getDocumentUrl({
      path: { document_id: document.document_id },
    }),
    refetchInterval: URL_REFRESH_MS,
    // The link is short-lived by design, so a cached one is worse than none.
    gcTime: URL_REFRESH_MS,
    staleTime: URL_REFRESH_MS,
  })

  if (link.isPending) {
    return <Skeleton className="h-[28rem] w-full rounded-lg" />
  }

  if (link.isError) {
    return (
      <Alert variant="destructive">
        <WarningIcon data-icon="inline-start" />
        <AlertTitle>This document could not be opened</AlertTitle>
        <AlertDescription>
          {link.error instanceof Error
            ? link.error.message
            : "The link could not be issued."}
        </AlertDescription>
      </Alert>
    )
  }

  const { url, content_type: contentType } = link.data

  if (IMAGE_TYPES.includes(contentType)) {
    return (
      <img
        src={url}
        // No applicant detail in the alt text: it is read aloud by screen
        // readers and copied into bug reports.
        alt={`${document.document_type} submitted with this application`}
        className="max-h-[28rem] w-full rounded-lg border object-contain"
        referrerPolicy="no-referrer"
      />
    )
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <Button
        variant="outline"
        size="sm"
        nativeButton={false}
        render={<a href={url} target="_blank" rel="noopener noreferrer" />}
      >
        <ArrowSquareOutIcon data-icon="inline-start" />
        Open in new tab
      </Button>
      <iframe
        src={url}
        title={`${document.document_type} submitted with this application`}
        className="h-[28rem] w-full rounded-lg border"
        referrerPolicy="no-referrer"
      />
    </div>
  )
}

/** The icon for a document of this type — a hint at what the viewer will do
 * with it, not a claim about the file. */
export function DocumentKindIcon({ contentType }: { contentType: string }) {
  return IMAGE_TYPES.includes(contentType) ? (
    <ImageIcon className="size-4 text-muted-foreground" />
  ) : (
    <FileTextIcon className="size-4 text-muted-foreground" />
  )
}
