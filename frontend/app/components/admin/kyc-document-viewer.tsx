import { FileTextIcon, ImageIcon, WarningIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Skeleton } from "~/components/ui/skeleton"
import type { KycDocument } from "~/lib/api"
import { useApi } from "~/lib/use-api"

/** Ask for a fresh link a little before the five-minute one expires, so a
 * reviewer reading a long document does not watch it go blank. */
const URL_REFRESH_MS = 4 * 60 * 1000

export const KYC_DOCUMENT_URL_KEY = "kyc-document-url"

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]

/**
 * Renders one uploaded document.
 *
 * An uploaded file is untrusted input from a stranger — the only untrusted
 * binary this platform accepts — so it is never injected as HTML and never
 * rendered in this page's origin. A PDF goes into a fully sandboxed iframe
 * (no scripts, no forms, no same-origin access, no popups); an image goes
 * into an `<img>`, which cannot execute anything at all. SVG is not in the
 * accepted set precisely because it would be a document rather than a
 * picture.
 *
 * The URL is fetched on demand rather than passed in: every issue of one is
 * recorded in the audit log against the reviewer who asked, and a link that
 * outlived the page it was rendered on would be a link nobody is accountable
 * for.
 */
export function KycDocumentViewer({ document }: { document: KycDocument }) {
  const api = useApi()

  const link = useQuery({
    queryKey: [KYC_DOCUMENT_URL_KEY, document.document_id],
    queryFn: () => api.getKycDocumentUrl(document.document_id),
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
    <iframe
      // Empty sandbox: everything the file might try is denied, including
      // script, same-origin access, form submission and top-level navigation.
      // If a browser will not render a PDF under it, that is the safe failure
      // — loosening the sandbox to make rendering work would defeat it.
      sandbox=""
      src={url}
      title={`${document.document_type} submitted with this application`}
      className="h-[28rem] w-full rounded-lg border bg-muted"
      referrerPolicy="no-referrer"
    />
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
