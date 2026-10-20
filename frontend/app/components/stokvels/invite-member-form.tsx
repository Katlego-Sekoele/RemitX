import { useMutation, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { useState } from "react"
import { toast } from "sonner"

import { AccountReference } from "~/components/accounts/reference"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { stokvelErrorMessage } from "~/lib/stokvel-errors"
import {
  invalidateStokvels,
  normaliseReference,
  pendingInvitations,
  stokvelMutations,
  type SentStokvelInvitationRead,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/**
 * The Organiser invites people by the fiat account reference they shared,
 * e.g. "thandi2-zar" (R4-04, #253), while the stokvel is being set up. The
 * API checks the rules (#230: verified, an account in the Stokvel currency,
 * not already in or invited) and words each refusal. Nobody joins until they
 * accept, and invitations still open when the cycle starts lapse. The page
 * shows this card only when `canInvite` holds. No Revoke until #297; no
 * WhatsApp share before the MVP (Sian, 16 Oct).
 */
export function InviteMemberForm({ stokvel }: { stokvel: StokvelDetailRead }) {
  const queryClient = useQueryClient()
  const [reference, setReference] = useState("")
  const invite = useMutation({
    ...stokvelMutations.invite(stokvel.stokvel_id),
    onSuccess: async (invitation) => {
      setReference("")
      await invalidateStokvels(queryClient)
      toast.success(
        `Invitation sent to ${invitation.invitee_name ?? invitation.account_reference}`
      )
    },
  })
  // References are stored lower-case and matched exactly.
  const normalised = normaliseReference(reference)
  const pending = pendingInvitations(stokvel)
  const currency = stokvel.currency.toLowerCase()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invite members</CardTitle>
        <CardDescription>
          Nobody joins until they accept, and invitations still open when you
          start the cycle lapse.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {pending.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {pending.map((invitation) => (
              <PendingInvitation
                key={invitation.invitation_id}
                invitation={invitation}
              />
            ))}
          </ul>
        ) : null}

        <form
          noValidate
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (normalised) invite.mutate({ account_reference: normalised })
          }}
        >
          <Field data-invalid={invite.isError}>
            <FieldLabel htmlFor="invite-reference">
              Their {stokvel.currency} account reference
            </FieldLabel>
            <div className="flex gap-2">
              <Input
                id="invite-reference"
                value={reference}
                placeholder={`thandi2-${currency}`}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                aria-invalid={invite.isError}
                onChange={(event) => {
                  setReference(event.target.value)
                  if (invite.isError) invite.reset()
                }}
              />
              <Button type="submit" disabled={!normalised || invite.isPending}>
                {invite.isPending ? "Inviting…" : "Invite"}
              </Button>
            </div>
            {invite.isError ? (
              <FieldError>{stokvelErrorMessage(invite.error)}</FieldError>
            ) : (
              <FieldDescription>
                Ask them for the reference on their Accounts page. They pay from
                that account, so it must be in {stokvel.currency}.
              </FieldDescription>
            )}
          </Field>
        </form>
      </CardContent>
    </Card>
  )
}

/** One pending invitation. The detail route (#355) leaves the reference null
 * for anyone but the Organiser, or when the invitee no longer holds the
 * account, so it is shown only when there is one. */
function PendingInvitation({
  invitation,
}: {
  invitation: Pick<SentStokvelInvitationRead, "invitee_name" | "created_at"> & {
    account_reference: string | null
  }
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2">
      <span className="flex flex-wrap items-center gap-2">
        {invitation.invitee_name ?? "Invited"}
        {invitation.account_reference ? (
          <AccountReference reference={invitation.account_reference} />
        ) : null}
      </span>
      <Badge variant="secondary">
        Invited{" "}
        {formatDistanceToNow(new Date(invitation.created_at), {
          addSuffix: true,
        })}
      </Badge>
    </li>
  )
}
