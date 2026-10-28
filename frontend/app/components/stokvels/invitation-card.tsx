import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router"
import { mutationToast } from "~/lib/mutation-toast"

import { ContributionAtTodaysRate } from "~/components/stokvels/contribution-at-rate"
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
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { FieldError } from "~/components/ui/field"
import {
  isGoneInvitationError,
  stokvelErrorMessage,
} from "~/lib/stokvel-errors"
import {
  invalidateStokvels,
  stokvelMutations,
  stokvelPath,
  type StokvelInvitationRead,
} from "~/lib/stokvels"

/**
 * An invitation the signed-in user has not answered (R4-04, #253). Joining
 * is a savings commitment, so only the invitee can accept; declining is
 * final, so it asks first. Unanswered invitations lapse when the Organiser
 * starts the cycle, and the card says so up front.
 */
export function InvitationCard({
  invitation,
}: {
  invitation: StokvelInvitationRead
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [confirmDecline, setConfirmDecline] = useState(false)

  // An invitation that has lapsed, been answered, or whose stokvel is gone
  // can't be answered again: refresh the list so the card disappears.
  const refreshIfGone = async (error: unknown) => {
    if (isGoneInvitationError(error)) await invalidateStokvels(queryClient)
  }
  const accept = useMutation({
    ...mutationToast(stokvelMutations.acceptInvitation(), {
      success: (stokvel) => `You've joined ${stokvel.name}`,
    }),
    onSuccess: async (stokvel) => {
      await invalidateStokvels(queryClient)
      navigate(stokvelPath(stokvel.stokvel_id))
    },
    onError: refreshIfGone,
  })
  const decline = useMutation({
    ...mutationToast(stokvelMutations.declineInvitation(), {
      success: `Invitation to ${invitation.stokvel_name} declined`,
    }),
    onSuccess: async () => {
      setConfirmDecline(false)
      await invalidateStokvels(queryClient)
    },
    onError: refreshIfGone,
  })
  const busy = accept.isPending || decline.isPending

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>{invitation.stokvel_name}</CardTitle>
          <Badge variant="secondary">Invitation</Badge>
        </div>
        <CardDescription>
          {invitation.invited_by_name ?? "A RemitX member"} invited you ·{" "}
          <ContributionAtTodaysRate
            amount={invitation.contribution_amount}
            currency={invitation.currency}
          />{" "}
          per round, paid from your {invitation.currency} account
        </CardDescription>
        <CardDescription>
          Answer before the organiser starts the cycle: invitations still open
          then lapse, and you&apos;d wait for the next cycle.
        </CardDescription>
      </CardHeader>
      {accept.isError ? (
        <CardContent>
          <FieldError>{stokvelErrorMessage(accept.error)}</FieldError>
        </CardContent>
      ) : null}
      <CardFooter className="flex-wrap gap-2">
        <Button
          size="sm"
          disabled={busy}
          onClick={() => accept.mutate(invitation.invitation_id)}
        >
          {accept.isPending ? "Joining…" : "Accept"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => setConfirmDecline(true)}
        >
          Decline
        </Button>
      </CardFooter>

      <AlertDialog
        open={confirmDecline}
        onOpenChange={(next) => {
          // Escape or a backdrop click mustn't close it mid-request: that
          // would re-enable Accept and drop the decline's own error.
          if (!next && decline.isPending) return
          setConfirmDecline(next)
          if (!next) decline.reset()
        }}
      >
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>
              Decline {invitation.stokvel_name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              You can only join later if the organiser invites you again.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {decline.isError ? (
            <FieldError>{stokvelErrorMessage(decline.error)}</FieldError>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={decline.isPending}>
              Keep
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={decline.isPending}
              onClick={(event) => {
                // Stay open until the decline has gone through or failed.
                event.preventDefault()
                decline.mutate(invitation.invitation_id)
              }}
            >
              {decline.isPending ? "Declining…" : "Decline"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
