import { ImageSquareIcon } from "@phosphor-icons/react"
import { useQueryClient } from "@tanstack/react-query"
import { useMutation } from "~/hooks/use-mutation"
import { useEffect, useId, useRef, useState, type ReactNode } from "react"
import { toast } from "sonner"

import { api } from "~/client"
import { Button } from "~/components/ui/button"
import { PageHeaderTitle } from "~/components/ui/page-header"
import { stokvelQueries } from "~/lib/stokvels"

const MAX_COVER_BYTES = 5 * 1024 * 1024

// Black at falling opacity, in srgb. A Tailwind `from-black/*` fade is
// interpolated in oklab and paints a solid band instead of a scrim.
const BANNER_SCRIM = [
  "linear-gradient(to top, rgb(0 0 0 / 0.55), rgb(0 0 0 / 0) 58%)",
  "linear-gradient(to right, rgb(0 0 0 / 0.82), rgb(0 0 0 / 0.4) 46%, rgb(0 0 0 / 0) 78%)",
].join(", ")

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
    toast: {
      loading: "Saving the cover photo…",
      success: "Cover photo saved",
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: stokvelQueries.list().queryKey,
      })
      void queryClient.invalidateQueries({
        queryKey: stokvelQueries.detail(stokvelId).queryKey,
      })
    },
  })

  function takeFile(file: File | undefined) {
    if (!file || upload.isPending) return
    if (file.size > MAX_COVER_BYTES) {
      toast.error("Cover photos are limited to 5 MB.")
      return
    }
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
        {/* srgb stops. Theme gradient utilities interpolate in oklab and
            turn a fade into a hard band. */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{ backgroundImage: BANNER_SCRIM }}
        />
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

/** List thumbnail. Fills the height of the card content, inside its padding. */
export function StokvelCoverThumb({
  coverUrl,
  onBroken,
}: {
  coverUrl: string
  onBroken: () => void
}) {
  return (
    <div className="relative w-20 shrink-0 self-stretch overflow-hidden rounded-lg">
      <img
        src={coverUrl}
        alt=""
        className="absolute inset-0 size-full object-cover"
        onError={onBroken}
      />
    </div>
  )
}
