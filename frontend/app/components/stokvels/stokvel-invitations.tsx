import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useMutation } from "~/hooks/use-mutation"
import { formatDistanceToNow } from "date-fns"
import { useState } from "react"
import { api, type BeneficiaryRead } from "~/client"
import { AccountReference } from "~/components/accounts/reference"
import { BeneficiaryAvatar } from "~/components/beneficiaries/beneficiary-avatar"
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
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { beneficiaryName, beneficiaryShortName } from "~/lib/beneficiaries"
import { isGoneInvitationError, revokeErrorMessage } from "~/lib/stokvel-errors"
import {
  InvitationStatus,
  invalidateStokvels,
  invitationBadges,
  invitationsAwaitingContinuation,
  invitationsByStatus,
  pendingInvitations,
  stokvelMutations,
  type InvitationBadge,
  type StokvelDetailInvitationRead,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/**
 * Every invitation of the stokvel and its status (R4-13, #299; all of them
 * since R2-17, #375), for every member while the stokvel is being set up:
 * the ones waiting for an answer first, then accepted, declined, revoked and
 * lapsed ones. The Organiser can revoke a pending one
 * (`POST /invitations/{id}/revoke`, #297); the person can then be invited
 * again.
 */
export function StokvelInvitations({
  stokvel,
}: {
  stokvel: StokvelDetailRead
}) {
  const invitations = invitationsByStatus(stokvel)
  const beneficiaries = useQuery(api.beneficiaries.listMyBeneficiaries())
  if (invitations.length === 0) return null
  const waiting =
    pendingInvitations(stokvel).length +
    invitationsAwaitingContinuation(stokvel).size
  const badges = invitationBadges(stokvel)
  const portraits = beneficiaries.data ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invitations</CardTitle>
        <CardDescription>
          {waiting === 0
            ? "Nobody is waiting to answer."
            : `${waiting} waiting for an answer.`}{" "}
          Invitations still open when the cycle starts lapse.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2">
          {invitations.map((invitation) => (
            <InvitationRow
              key={invitation.invitation_id}
              invitation={invitation}
              portrait={inviteePortrait(invitation.invitee_name, portraits)}
              badge={badges.get(invitation.invitation_id)!}
              canRevoke={
                stokvel.is_organiser &&
                invitation.status === InvitationStatus.pending
              }
            />
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

/** The Organiser's beneficiary photo when the invitee is one of them. */
function inviteePortrait(
  name: string | null,
  beneficiaries: readonly BeneficiaryRead[]
): BeneficiaryRead | { full_name: string; profile_image_url: null } {
  const label = name ?? "Invited"
  const match = name
    ? beneficiaries.find((beneficiary) => {
        const full = beneficiaryName(beneficiary)
        return full === name || beneficiaryShortName(beneficiary) === name
      })
    : undefined
  return match ?? { full_name: label, profile_image_url: null }
}

/** One invitation and its status. The detail route leaves the reference
 * null for anyone but the Organiser, or when the invitee no longer holds
 * the account, so it is shown only when there is one. `badge` comes from
 * `invitationBadges`. */
function InvitationRow({
  invitation,
  portrait,
  badge,
  canRevoke,
}: {
  invitation: StokvelDetailInvitationRead
  portrait: BeneficiaryRead | { full_name: string; profile_image_url: null }
  badge: InvitationBadge
  canRevoke: boolean
}) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const name = invitation.invitee_name ?? "this person"
  const pending = invitation.status === InvitationStatus.pending
  const revoke = useMutation({
    ...stokvelMutations.revokeInvitation(),
    toast: {
      success: `Invitation to ${name} revoked`,
      error: (error) => revokeErrorMessage(error),
    },
    onSuccess: async () => {
      setConfirming(false)
      await invalidateStokvels(queryClient)
    },
    onError: async (error) => {
      // Answered, lapsed or gone in the meantime: refresh so it disappears.
      if (isGoneInvitationError(error)) await invalidateStokvels(queryClient)
    },
  })

  return (
    <li>
      <Item variant="outline">
        <ItemMedia>
          <BeneficiaryAvatar beneficiary={portrait} />
        </ItemMedia>
        <ItemContent>
          <ItemTitle>{invitation.invitee_name ?? "Invited"}</ItemTitle>
          {invitation.account_reference ? (
            <AccountReference reference={invitation.account_reference} />
          ) : null}
          {pending ? (
            <ItemDescription>
              Invited{" "}
              {formatDistanceToNow(new Date(invitation.created_at), {
                addSuffix: true,
              })}
            </ItemDescription>
          ) : null}
        </ItemContent>
        <ItemActions>
          <Badge variant={badge.variant}>{badge.label}</Badge>
          {canRevoke ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirming(true)}
            >
              Revoke
            </Button>
          ) : null}
        </ItemActions>
      </Item>

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
