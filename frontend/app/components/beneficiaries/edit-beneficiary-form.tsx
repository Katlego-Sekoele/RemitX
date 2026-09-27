import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { toast } from "sonner"

import {
  api,
  type BeneficiaryRead,
  type BeneficiaryRelationship,
  type PayoutCurrency,
} from "~/client"
import {
  PayoutCurrencyField,
  RelationshipField,
} from "~/components/beneficiaries/beneficiary-fields"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { FieldGroup } from "~/components/ui/field"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "~/components/ui/item"
import { errorMessage } from "~/hooks/use-onboarding"
import {
  beneficiaryName,
  beneficiaryPayoutCurrencies,
  invalidateBeneficiaries,
} from "~/lib/beneficiaries"

/** Change a beneficiary's payout currency or relationship, in place on the
 * list. The person is fixed: a different person is a different beneficiary.
 * Nothing here is final, so it is not a modal — cancelling leaves the saved
 * values, and saving can be edited again. */
export function EditBeneficiaryForm({
  beneficiary,
  onCancel,
  onSaved,
}: {
  beneficiary: BeneficiaryRead
  onCancel: () => void
  onSaved: () => void
}) {
  const queryClient = useQueryClient()
  const name = beneficiaryName(beneficiary)
  const [payoutCurrency, setPayoutCurrency] = useState<PayoutCurrency>(
    beneficiary.payout_currency
  )
  const payoutOptions = beneficiaryPayoutCurrencies(beneficiary)
  const [relationship, setRelationship] = useState<BeneficiaryRelationship>(
    beneficiary.relationship
  )
  const update = useMutation({
    ...api.beneficiaries.updateBeneficiary(),
    onSuccess: async () => {
      await invalidateBeneficiaries(queryClient)
      toast.success(`${name} updated`)
      onSaved()
    },
  })
  const changed = {
    ...(payoutCurrency !== beneficiary.payout_currency
      ? { payout_currency: payoutCurrency }
      : {}),
    ...(relationship !== beneficiary.relationship ? { relationship } : {}),
  }
  const dirty = Object.keys(changed).length > 0

  return (
    <form
      noValidate
      role="listitem"
      onSubmit={(event) => {
        event.preventDefault()
        if (!dirty) return
        update.mutate({
          path: { beneficiary_id: beneficiary.beneficiary_id },
          body: changed,
        })
      }}
    >
      <Card>
        <CardHeader>
          <CardTitle>Edit beneficiary</CardTitle>
          <CardDescription>
            Change how {name} is paid, or how you know them.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Item variant="muted">
            <ItemContent>
              <ItemTitle>
                {[name, beneficiary.country_name].filter(Boolean).join(" · ")}
              </ItemTitle>
              <ItemDescription>
                These come from their verified profile.
              </ItemDescription>
            </ItemContent>
          </Item>
          <FieldGroup>
            <PayoutCurrencyField
              id={`edit-${beneficiary.beneficiary_id}-payout-currency`}
              value={payoutCurrency}
              options={payoutOptions}
              onChange={setPayoutCurrency}
            />
            <RelationshipField
              id={`edit-${beneficiary.beneficiary_id}-relationship`}
              value={relationship}
              onChange={setRelationship}
            />
          </FieldGroup>
          {update.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(update.error)}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
        <CardFooter className="flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={update.isPending}
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={!dirty || update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}
