import { ImageSquareIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useId, useRef, useState, type ReactNode } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import { api } from "~/client"
import { Button } from "~/components/ui/button"
import { PageHeaderTitle } from "~/components/ui/page-header"
import { errorMessage } from "~/hooks/use-onboarding"
import { stokvelPath, stokvelQueries } from "~/lib/stokvels"

const MAX_COVER_BYTES = 5 * 1024 * 1024

function toastId(stokvelId: string) {
  return `stokvel-cover-${stokvelId}`
}

function CoverPhotoButton({
  stokvelId,
  label,
}: {
  stokvelId: string
  label: string
}) {
  const inputId = useId()
  const input = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const upload = useMutation({
    ...api.stokvels.uploadStokvelCover(),
    onSuccess: () => {
      toast.success("Cover photo saved", { id: toastId(stokvelId) })
      void queryClient.invalidateQueries({
        queryKey: stokvelQueries.list().queryKey,
      })
      void queryClient.invalidateQueries({
        queryKey: stokvelQueries.detail(stokvelId).queryKey,
      })
    },
    onError: (error) => {
      toast.error(errorMessage(error), { id: toastId(stokvelId) })
    },
  })

  function takeFile(file: File | undefined) {
    if (!file || upload.isPending) return
    if (file.size > MAX_COVER_BYTES) {
      toast.error("Cover photos are limited to 5 MB.")
      return
    }
    toast.loading("Saving the cover photo…", { id: toastId(stokvelId) })
    upload.mutate({
      path: { stokvel_id: stokvelId },
      body: file,
      headers: { "Content-Type": file.type || null },
    })
    if (input.current) input.current.value = ""
  }

  return (
    <>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={upload.isPending}
        onClick={() => input.current?.click()}
      >
        <ImageSquareIcon data-icon="inline-start" />
        {label}
      </Button>
      <input
        id={inputId}
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        aria-label={label}
        className="sr-only"
        onChange={(event) => takeFile(event.currentTarget.files?.[0])}
      />
    </>
  )
}

/** The stokvel name on its cover, or the plain title when there is no photo. */
export function StokvelCoverBanner({
  name,
  coverUrl,
  stokvelId,
  canEdit,
  badge,
}: {
  name: string
  coverUrl: string | null
  stokvelId: string
  canEdit: boolean
  badge: ReactNode
}) {
  const [broken, setBroken] = useState(false)
  useEffect(() => {
    setBroken(false)
  }, [coverUrl])
  const visible = Boolean(coverUrl) && !broken

  if (!visible) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <PageHeaderTitle>{name}</PageHeaderTitle>
        {badge}
        {canEdit ? (
          <CoverPhotoButton stokvelId={stokvelId} label="Add a cover photo" />
        ) : null}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative isolate overflow-hidden rounded-xl">
        <img
          src={coverUrl ?? undefined}
          alt=""
          className="aspect-[2.4/1] max-h-64 w-full object-cover"
          onError={() => setBroken(true)}
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-black/80 via-black/45 to-black/5" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-black/20" />
        <div className="absolute inset-0 flex items-end p-5 sm:p-7">
          <PageHeaderTitle className="text-white drop-shadow-md">
            {name}
          </PageHeaderTitle>
        </div>
        {canEdit ? (
          <div className="absolute top-3 right-3">
            <CoverPhotoButton stokvelId={stokvelId} label="Change cover" />
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-3">{badge}</div>
    </div>
  )
}

/** The same photo as a list thumbnail, with the name on a dark gradient. */
export function StokvelCoverThumb({
  name,
  coverUrl,
  stokvelId,
  badge,
  onBroken,
}: {
  name: string
  coverUrl: string
  stokvelId: string
  badge: ReactNode
  onBroken: () => void
}) {
  return (
    <div className="relative -mt-(--card-spacing)">
      <Link to={stokvelPath(stokvelId)} className="relative block">
        <img
          src={coverUrl}
          alt=""
          className="aspect-[2.4/1] w-full object-cover"
          onError={onBroken}
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/80 via-black/35 to-black/10" />
        <span className="absolute inset-x-0 bottom-0 p-4 font-heading text-lg font-semibold text-white drop-shadow-md">
          {name}
        </span>
      </Link>
      {badge ? (
        <div className="pointer-events-none absolute top-3 right-3">
          {badge}
        </div>
      ) : null}
    </div>
  )
}
