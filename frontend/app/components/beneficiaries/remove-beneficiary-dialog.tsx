import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, type BeneficiaryRead } from "~/client"
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
import { FieldError } from "~/components/ui/field"
import { errorMessage } from "~/hooks/use-onboarding"
import {
  beneficiaryShortName,
  invalidateBeneficiaries,
} from "~/lib/beneficiaries"

/** Confirm, then remove a beneficiary for good. Removal is final, so it
 * is the one step that uses a modal. Transfers to them stay in the sender's
 * history: those point at the person, not this entry. */
export function RemoveBeneficiaryDialog({
  beneficiary,
  open,
  onOpenChange,
}: {
  beneficiary: BeneficiaryRead
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const name = beneficiaryShortName(beneficiary)
  const remove = useMutation({
    ...api.beneficiaries.deleteBeneficiary(),
    onSuccess: async () => {
      onOpenChange(false)
      await invalidateBeneficiaries(queryClient)
      toast.success(`${name} removed`)
    },
  })

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) remove.reset()
      }}
    >
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {name}?</AlertDialogTitle>
          <AlertDialogDescription>
            Past transfers stay in your history.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {remove.isError ? (
          <FieldError>{errorMessage(remove.error)}</FieldError>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={remove.isPending}>
            Keep
          </AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate({
                path: { beneficiary_id: beneficiary.beneficiary_id },
              })
            }
          >
            {remove.isPending ? "Removing…" : "Remove"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
