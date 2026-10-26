import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { toast } from "sonner"

import { api, type BeneficiaryRead } from "~/client"
import { AddBeneficiaryForm } from "~/components/beneficiaries/add-beneficiary-form"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import { beneficiaryName } from "~/lib/beneficiaries"
import { stokvelErrorMessage } from "~/lib/stokvel-errors"
import {
  invalidateStokvels,
  invitableBeneficiaries,
  normaliseReference,
  stokvelMutations,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/** Which field the last invite came from, so its refusal shows there. */
type InviteBy = "beneficiary" | "reference"

/**
 * The Organiser invites people while the stokvel is being set up: one of
 * their beneficiaries from a dropdown, like choosing a payout beneficiary
 * (`beneficiary_id` on `POST /stokvels/{id}/invitations`), or anyone by the
 * fiat account reference they shared, e.g. "thandi2-zar", without saving
 * them as a beneficiary. Add a beneficiary uses the app's own form. Only
 * beneficiaries with an account in the Stokvel currency, which they'd pay
 * from, are offered, and current members are left out. The API checks the
 * rest (#230: verified, the right currency, not already invited) and words
 * each refusal. Nobody joins until they accept, and invitations still open
 * when the cycle starts lapse. The page shows this card only when
 * `canInvite` holds; who is invited, and Revoke, are on
 * `StokvelInvitations` (#299).
 */
export function InviteMemberForm({ stokvel }: { stokvel: StokvelDetailRead }) {
  const queryClient = useQueryClient()
  const beneficiaries = useQuery(api.beneficiaries.listMyBeneficiaries())
  const [beneficiaryId, setBeneficiaryId] = useState("")
  const [reference, setReference] = useState("")
  const [inviteBy, setInviteBy] = useState<InviteBy>("beneficiary")
  const [adding, setAdding] = useState(false)
  const invite = useMutation({
    ...stokvelMutations.invite(stokvel.stokvel_id),
    onSuccess: async (invitation) => {
      setBeneficiaryId("")
      setReference("")
      await invalidateStokvels(queryClient)
      toast.success(
        `Invitation sent to ${invitation.invitee_name ?? invitation.account_reference}`
      )
    },
  })

  const { invitable, otherCurrency } = invitableBeneficiaries(
    beneficiaries.data ?? [],
    stokvel
  )
  const chosen = invitable.find((b) => b.beneficiary_id === beneficiaryId)
  const items = invitable.map((b) => ({
    value: b.beneficiary_id,
    label: beneficiaryName(b),
  }))
  // References are stored lower-case and matched exactly.
  const normalised = normaliseReference(reference)
  const currency = stokvel.currency.toLowerCase()
  const refusal = (by: InviteBy) =>
    invite.isError && inviteBy === by ? stokvelErrorMessage(invite.error) : null

  function inviteWith(by: InviteBy) {
    setInviteBy(by)
    if (by === "beneficiary" && chosen) {
      invite.mutate({ beneficiary_id: chosen.beneficiary_id })
    } else if (by === "reference" && normalised) {
      invite.mutate({ account_reference: normalised })
    }
  }

  if (adding) {
    return (
      <AddBeneficiaryForm
        onCancel={() => setAdding(false)}
        onAdded={async (beneficiary: BeneficiaryRead) => {
          setAdding(false)
          await queryClient.invalidateQueries({
            queryKey: api.beneficiaries.listMyBeneficiaries().queryKey,
          })
          if (beneficiary.payout_currencies.includes(stokvel.currency)) {
            setBeneficiaryId(beneficiary.beneficiary_id)
          }
        }}
      />
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invite members</CardTitle>
        <CardDescription>
          Nobody joins until they accept, and invitations still open when you
          start the cycle lapse.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <FieldGroup>
          {beneficiaries.isPending ? (
            <Skeleton className="h-16 w-full" />
          ) : beneficiaries.isError ? (
            <FieldError>{errorMessage(beneficiaries.error)}</FieldError>
          ) : invitable.length > 0 ? (
            <form
              noValidate
              onSubmit={(event) => {
                event.preventDefault()
                inviteWith("beneficiary")
              }}
            >
              <Field data-invalid={refusal("beneficiary") !== null}>
                <FieldLabel htmlFor="invite-beneficiary">
                  From your beneficiaries
                </FieldLabel>
                <div className="flex gap-2">
                  <Select
                    items={items}
                    value={beneficiaryId || null}
                    onValueChange={(next) => {
                      setBeneficiaryId(next ?? "")
                      if (invite.isError) invite.reset()
                    }}
                  >
                    <SelectTrigger id="invite-beneficiary" className="w-full">
                      <SelectValue placeholder="Choose who to invite" />
                    </SelectTrigger>
                    <SelectContent alignItemWithTrigger={false}>
                      {items.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button type="submit" disabled={!chosen || invite.isPending}>
                    {invite.isPending && inviteBy === "beneficiary"
                      ? "Inviting…"
                      : "Invite"}
                  </Button>
                </div>
                {refusal("beneficiary") ? (
                  <FieldError>{refusal("beneficiary")}</FieldError>
                ) : otherCurrency > 0 ? (
                  <FieldDescription>
                    {otherCurrency === 1
                      ? "1 beneficiary isn't listed: they have"
                      : `${otherCurrency} beneficiaries aren't listed: they have`}{" "}
                    no {stokvel.currency} account to pay from.
                  </FieldDescription>
                ) : null}
              </Field>
            </form>
          ) : (
            <FieldDescription>
              None of your beneficiaries can join this stokvel. Invite someone
              by their account reference below, or add them as a beneficiary.
            </FieldDescription>
          )}

          <FieldSeparator>Or</FieldSeparator>

          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault()
              inviteWith("reference")
            }}
          >
            <Field data-invalid={refusal("reference") !== null}>
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
                  aria-invalid={refusal("reference") !== null}
                  onChange={(event) => {
                    setReference(event.target.value)
                    if (invite.isError) invite.reset()
                  }}
                />
                <Button
                  type="submit"
                  disabled={!normalised || invite.isPending}
                >
                  {invite.isPending && inviteBy === "reference"
                    ? "Inviting…"
                    : "Invite"}
                </Button>
              </div>
              {refusal("reference") ? (
                <FieldError>{refusal("reference")}</FieldError>
              ) : (
                <FieldDescription>
                  For someone who isn&apos;t one of your beneficiaries. Ask them
                  for the reference on their Accounts page.
                </FieldDescription>
              )}
            </Field>
          </form>
        </FieldGroup>
      </CardContent>
      <CardFooter>
        <Button type="button" variant="outline" onClick={() => setAdding(true)}>
          Add a beneficiary
        </Button>
      </CardFooter>
    </Card>
  )
}
