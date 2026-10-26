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
} from "~/components/ui/field"
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
  stokvelMutations,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/**
 * The Organiser invites people from their beneficiaries, like choosing a
 * payout beneficiary (`beneficiary_id` on `POST /stokvels/{id}/invitations`),
 * while the stokvel is being set up. Someone new is added with the app's own
 * beneficiary form first. Only beneficiaries with an account in the Stokvel
 * currency are offered, since they pay from it, and current members are left
 * out. The API checks the rest (#230: verified, not already invited) and
 * words each refusal. Nobody joins until they accept, and invitations still
 * open when the cycle starts lapse. The page shows this card only when
 * `canInvite` holds; who is invited, and Revoke, are on `StokvelInvitations`
 * (#299).
 */
export function InviteMemberForm({ stokvel }: { stokvel: StokvelDetailRead }) {
  const queryClient = useQueryClient()
  const beneficiaries = useQuery(api.beneficiaries.listMyBeneficiaries())
  const [beneficiaryId, setBeneficiaryId] = useState("")
  const [adding, setAdding] = useState(false)
  const invite = useMutation({
    ...stokvelMutations.invite(stokvel.stokvel_id),
    onSuccess: async (invitation) => {
      setBeneficiaryId("")
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
      <form
        noValidate
        className="flex flex-col gap-(--card-spacing)"
        onSubmit={(event) => {
          event.preventDefault()
          if (chosen) invite.mutate({ beneficiary_id: chosen.beneficiary_id })
        }}
      >
        <CardHeader>
          <CardTitle>Invite members</CardTitle>
          <CardDescription>
            Nobody joins until they accept, and invitations still open when you
            start the cycle lapse.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {beneficiaries.isPending ? (
            <Skeleton className="h-16 w-full" />
          ) : beneficiaries.isError ? (
            <FieldError>{errorMessage(beneficiaries.error)}</FieldError>
          ) : (
            <FieldGroup>
              {invitable.length > 0 ? (
                <Field data-invalid={invite.isError}>
                  <FieldLabel htmlFor="invite-beneficiary">
                    Beneficiary
                  </FieldLabel>
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
                  {invite.isError ? (
                    <FieldError>{stokvelErrorMessage(invite.error)}</FieldError>
                  ) : (
                    <FieldDescription>
                      They pay from their {stokvel.currency} account.
                    </FieldDescription>
                  )}
                </Field>
              ) : (
                <FieldDescription>
                  None of your beneficiaries can join yet. Add the person you
                  want to invite as a beneficiary first.
                </FieldDescription>
              )}
              {otherCurrency > 0 ? (
                <FieldDescription>
                  {otherCurrency === 1
                    ? "1 beneficiary isn't listed: they have"
                    : `${otherCurrency} beneficiaries aren't listed: they have`}{" "}
                  no {stokvel.currency} account to pay from.
                </FieldDescription>
              ) : null}
            </FieldGroup>
          )}
        </CardContent>
        <CardFooter className="flex-wrap justify-between gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => setAdding(true)}
          >
            Add a beneficiary
          </Button>
          <Button type="submit" disabled={!chosen || invite.isPending}>
            {invite.isPending ? "Inviting…" : "Invite"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
