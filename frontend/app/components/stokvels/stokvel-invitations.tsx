import { useMutation, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { useState } from "react"
import { toast } from "sonner"

import { AccountReference } from "~/components/accounts/reference"
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
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { FieldError } from "~/components/ui/field"
import { isGoneInvitationError, revokeErrorMessage } from "~/lib/stokvel-errors"
import {
  invalidateStokvels,
  pendingInvitations,
  stokvelMutations,
  type StokvelDetailInvitationRead,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/**
 * Who has been invited and not answered yet (R4-13, #299), for every member
 * while the stokvel is being set up. The Organiser can revoke one
 * (`POST /invitations/{id}/revoke`, #297); the person can then be invited
 * again. `GET /stokvels/{id}` returns every invitation whatever its status
 * (R2-17, #375); this card lists only the pending ones.
 */
export function StokvelInvitations({
  stokvel,
}: {
  stokvel: StokvelDetailRead
}) {
  const pending = pendingInvitations(stokvel)
  if (pending.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invitations</CardTitle>
        <CardDescription>
          Waiting for an answer. Invitations still open when the cycle starts
          lapse.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-3">
          {pending.map((invitation) => (
            <PendingInvitation
              key={invitation.invitation_id}
              invitation={invitation}
              canRevoke={stokvel.is_organiser}
            />
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

/** One pending invitation. The detail route leaves the reference null for
 * anyone but the Organiser, or when the invitee no longer holds the account,
 * so it is shown only when there is one. */
function PendingInvitation({
  invitation,
  canRevoke,
}: {
  invitation: StokvelDetailInvitationRead
  canRevoke: boolean
}) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const name = invitation.invitee_name ?? "this person"
  const revoke = useMutation({
    ...stokvelMutations.revokeInvitation(),
    onSuccess: async () => {
      setConfirming(false)
      await invalidateStokvels(queryClient)
      toast.success(`Invitation to ${name} revoked`)
    },
    onError: async (error) => {
      // Answered, lapsed or gone in the meantime: refresh so it disappears.
      if (isGoneInvitationError(error)) await invalidateStokvels(queryClient)
    },
  })

  return (
    <li className="flex flex-wrap items-center justify-between gap-2">
      <span className="flex flex-wrap items-center gap-2">
        {invitation.invitee_name ?? "Invited"}
        {invitation.account_reference ? (
          <AccountReference reference={invitation.account_reference} />
        ) : null}
      </span>
      <span className="flex items-center gap-2">
        <Badge variant="secondary">
          Invited{" "}
          {formatDistanceToNow(new Date(invitation.created_at), {
            addSuffix: true,
          })}
        </Badge>
        {canRevoke ? (
          <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
            Revoke
          </Button>
        ) : null}
      </span>

      <AlertDialog
        open={confirming}
        onOpenChange={(next) => {
          // Not mid-request: closing would drop the revoke's own error.
          if (!next && revoke.isPending) return
          setConfirming(next)
          if (!next) revoke.reset()
        }}
      >
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>
              Revoke the invitation to {name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              They won&apos;t be able to join with it. You can invite them again
              later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {revoke.isError ? (
            <FieldError>{revokeErrorMessage(revoke.error)}</FieldError>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={revoke.isPending}>
              Keep
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={revoke.isPending}
              onClick={(event) => {
                // Stay open until the revoke has gone through or failed.
                event.preventDefault()
                revoke.mutate(invitation.invitation_id)
              }}
            >
              {revoke.isPending ? "Revoking…" : "Revoke"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  )
}
