import {
  ArrowSquareOutIcon,
  CircleNotchIcon,
  FileIcon,
  FilePdfIcon,
  ImageIcon,
  TrashIcon,
  UploadSimpleIcon,
} from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useId, useState } from "react"

import {
  Attachment,
  AttachmentAction,
  AttachmentActions,
  AttachmentContent,
  AttachmentDescription,
  AttachmentMedia,
  AttachmentTitle,
} from "~/components/ui/attachment"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "~/components/ui/alert-dialog"
import { FieldError } from "~/components/ui/field"
import { api, sdk, type KycDocumentRead as KycDocument } from "~/client"
import { errorMessage } from "~/hooks/use-onboarding"
import { toast } from "sonner"

const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf"
const MAX_BYTES = 10 * 1024 * 1024

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function typeLabel(contentType: string): string {
  if (contentType === "application/pdf") return "PDF"
  if (contentType === "image/jpeg") return "JPEG"
  if (contentType === "image/png") return "PNG"
  if (contentType === "image/webp") return "WebP"
  return contentType
}

function FileKindIcon({ contentType }: { contentType: string }) {
  if (contentType === "application/pdf") return <FilePdfIcon />
  if (contentType.startsWith("image/")) return <ImageIcon />
  return <FileIcon />
}

function StoredAttachment({
  document,
  onRemoved,
}: {
  document: KycDocument
  onRemoved: () => void
}) {
  const [opening, setOpening] = useState(false)
  const [openError, setOpenError] = useState<string | null>(null)
  const failed = document.status !== "stored"
  const uploaded = new Date(document.uploaded_at).toLocaleDateString()
  const label = typeLabel(document.content_type)
  const remove = useMutation({
    ...api.kyc.documents.removeMyDocument(),
    onSuccess: () => {
      toast.success(`${label} removed`)
      onRemoved()
    },
    onError: (error) => setOpenError(errorMessage(error)),
  })

  async function openDocument() {
    if (failed || opening) return
    setOpening(true)
    setOpenError(null)
    try {
      const { data: access } = await sdk.kyc.documents.getMyDocumentUrl({
        path: { document_id: document.document_id },
        throwOnError: true,
      })
      window.open(access.url, "_blank", "noopener,noreferrer")
    } catch (error) {
      setOpenError(errorMessage(error))
    } finally {
      setOpening(false)
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <Attachment
        className="w-full max-w-full"
        state={failed ? "error" : remove.isPending ? "processing" : "done"}
      >
        <AttachmentMedia variant="icon">
          <FileKindIcon contentType={document.content_type} />
        </AttachmentMedia>
        <AttachmentContent>
          <AttachmentTitle>
            {failed ? "Upload did not store" : `${label} scan`}
          </AttachmentTitle>
          <AttachmentDescription>
            {failed
              ? "Try another file. A reviewer cannot see this one."
              : `${label} · ${formatBytes(document.size_bytes)} · ${uploaded}`}
          </AttachmentDescription>
        </AttachmentContent>
        <AttachmentActions>
          {!failed ? (
            <AttachmentAction
              type="button"
              size="icon-sm"
              disabled={opening}
              aria-label={`Open uploaded ${label.toLowerCase()} scan`}
              onClick={() => void openDocument()}
            >
              {opening ? (
                <CircleNotchIcon className="animate-spin" aria-hidden="true" />
              ) : (
                <ArrowSquareOutIcon aria-hidden="true" />
              )}
            </AttachmentAction>
          ) : null}
          {document.removable ? (
            <AlertDialog>
              <AlertDialogTrigger
                render={
                  <AttachmentAction
                    type="button"
                    size="icon-sm"
                    disabled={remove.isPending}
                    aria-label={`Remove uploaded ${label.toLowerCase()} scan`}
                  />
                }
              >
                <TrashIcon aria-hidden="true" />
              </AlertDialogTrigger>
              <AlertDialogContent size="sm">
                <AlertDialogHeader>
                  <AlertDialogTitle>Remove this document?</AlertDialogTitle>
                  <AlertDialogDescription>
                    You can upload a different file afterwards.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep it</AlertDialogCancel>
                  <AlertDialogAction
                    variant="destructive"
                    onClick={() =>
                      remove.mutate({
                        path: { document_id: document.document_id },
                      })
                    }
                  >
                    Remove
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : null}
        </AttachmentActions>
      </Attachment>
      {openError ? <FieldError>{openError}</FieldError> : null}
    </div>
  )
}

export function KycDocumentUpload({
  id,
  applicationId,
  documentType,
  hint,
  onError,
}: {
  id: string
  applicationId: string | undefined
  documentType: "id_document" | "proof_of_address"
  hint: string
  onError: (message: string | null) => void
}) {
  const queryClient = useQueryClient()
  const generatedId = useId()
  const inputId = id || generatedId
  const [dragging, setDragging] = useState(false)
  const [pendingName, setPendingName] = useState<string | null>(null)

  const documentsQuery = { query: { application_id: applicationId ?? "" } }
  const documents = useQuery({
    ...api.kyc.documents.listMyDocuments(documentsQuery),
    enabled: Boolean(applicationId),
  })

  function refresh() {
    queryClient.invalidateQueries({
      queryKey: api.kyc.documents.listMyDocuments(documentsQuery).queryKey,
    })
    if (applicationId) {
      // The step checks which documents are stored off the application.
      queryClient.invalidateQueries({
        queryKey: api.kyc.onboarding.getMyApplication({
          path: { application_id: applicationId },
        }).queryKey,
      })
    }
  }

  const upload = useMutation({
    ...api.kyc.documents.uploadDocument(),
    onSuccess: () => {
      setPendingName(null)
      onError(null)
      refresh()
    },
    onError: (error) => {
      setPendingName(null)
      onError(errorMessage(error))
    },
  })

  const stored = (documents.data ?? []).filter(
    (doc) => doc.document_type === documentType
  )

  function takeFile(file: File | undefined) {
    if (!file || !applicationId || upload.isPending) return
    if (file.size > MAX_BYTES) {
      onError("Documents are limited to 10 MB.")
      return
    }
    setPendingName(file.name)
    onError(null)
    upload.mutate({
      query: { application_id: applicationId!, document_type: documentType },
      body: file,
      // The file's own type, which the API holds to its leading bytes. An
      // empty one is dropped (null) so the API can say it needs one, rather
      // than the spec's first listed type being sent in its place.
      headers: { "Content-Type": file.type || null },
    })
  }

  return (
    <div className="flex flex-col gap-3">
      <Attachment
        state="idle"
        data-dragging={dragging}
        aria-disabled={!applicationId || upload.isPending}
        className="min-h-24 w-full max-w-full justify-center"
      >
        <input
          id={inputId}
          type="file"
          accept={ACCEPT}
          disabled={!applicationId || upload.isPending}
          className="absolute inset-0 cursor-pointer opacity-0 disabled:cursor-not-allowed"
          onDragEnter={() => setDragging(true)}
          onDragLeave={() => setDragging(false)}
          onDrop={() => setDragging(false)}
          onChange={(event) => {
            takeFile(event.target.files?.[0])
            event.target.value = ""
          }}
        />
        <AttachmentMedia variant="icon">
          <UploadSimpleIcon aria-hidden="true" />
        </AttachmentMedia>
        <AttachmentContent>
          <AttachmentTitle>
            Drop a file here, or click to browse
          </AttachmentTitle>
          <AttachmentDescription>{hint}</AttachmentDescription>
        </AttachmentContent>
      </Attachment>
      {upload.isPending && pendingName ? (
        <Attachment className="w-full max-w-full" state="uploading">
          <AttachmentMedia>
            <CircleNotchIcon className="animate-spin" aria-hidden="true" />
          </AttachmentMedia>
          <AttachmentContent>
            <AttachmentTitle>{pendingName}</AttachmentTitle>
            <AttachmentDescription>Uploading…</AttachmentDescription>
          </AttachmentContent>
        </Attachment>
      ) : null}
      {stored.length > 0 ? (
        <div className="flex flex-col gap-2">
          {stored.map((document) => (
            <StoredAttachment
              key={document.document_id}
              document={document}
              onRemoved={refresh}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}
