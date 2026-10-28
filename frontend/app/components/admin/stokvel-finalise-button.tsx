import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { mutationToast } from "~/lib/mutation-toast"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog"
import { Button } from "~/components/ui/button"
import { FieldError } from "~/components/ui/field"
import {
  canReleaseByHand,
  finaliseHint,
  finaliseRefusalMessage,
  invalidateAdminRounds,
  stokvelAdminMutations,
  type AdminStokvelRoundRead,
} from "~/lib/stokvel-admin"

/**
 * Release one round by hand (R4-11, #260): only when the API marks the round
 * `manual_release_allowed` (fully paid, payout time passed, release pending).
 */
export function StokvelFinaliseButton({
  round,
}: {
  round: AdminStokvelRoundRead
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const finalise = useMutation({
    ...mutationToast(stokvelAdminMutations.finalise(), {
      success: `${round.stokvel_name}, round ${round.round + 1}: release queued`,
      error: (error) => finaliseRefusalMessage(error),
    }),
    onSuccess: async () => {
      setOpen(false)
      await invalidateAdminRounds(queryClient)
    },
  })
  const hint = finaliseHint(round)

  if (!canReleaseByHand(round)) return null

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Release payout
      </Button>
      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) finalise.reset()
        }}
      >
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>
              Release round {round.round + 1} of {round.stokvel_name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              The pool goes to {round.recipient_name}&apos;s beneficiary. Use
              this only when the automatic release hasn&apos;t happened. The
              contract still has the last word, and your name is recorded in the
              audit log.
              {round.release_status === "failed"
                ? " The automatic release failed for this round."
                : ""}
              {hint ? ` Note: ${hint}` : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {finalise.isError ? (
            <FieldError>{finaliseRefusalMessage(finalise.error)}</FieldError>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={finalise.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={finalise.isPending}
              onClick={(event) => {
                // Keep the dialog open to show a refusal.
                event.preventDefault()
                finalise.mutate({
                  stokvel_id: round.stokvel_id,
                  round: round.round,
                })
              }}
            >
              {finalise.isPending ? "Releasing…" : "Release payout"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
