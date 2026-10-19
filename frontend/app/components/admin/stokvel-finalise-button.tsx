import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { toast } from "sonner"

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
  finaliseHint,
  finaliseRefusalMessage,
  invalidateAdminRounds,
  stokvelAdminMutations,
  type AdminStokvelRoundRead,
} from "~/lib/stokvel-admin"

/**
 * Release one round by hand (R4-11, #260): the fallback when the automatic
 * release fails. It asks first, and the contract still checks the round is
 * fully paid and past its payout time, so an early try is refused with
 * "This round can't be paid out yet." (the demo's rejected early release).
 */
export function StokvelFinaliseButton({
  round,
}: {
  round: AdminStokvelRoundRead
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const finalise = useMutation({
    ...stokvelAdminMutations.finalise(),
    onSuccess: async () => {
      setOpen(false)
      await invalidateAdminRounds(queryClient)
      toast.success(
        `${round.stokvel_name}, round ${round.round + 1}: payout released`
      )
    },
  })
  const hint = finaliseHint(round)

  if (round.release_status === "released") return null

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
              contract still checks that everyone has paid and the payout time
              has passed, and your name is recorded in the audit log.
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
