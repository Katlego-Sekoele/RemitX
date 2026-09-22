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
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog"
import { FieldGroup } from "~/components/ui/field"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "~/components/ui/item"
import { errorMessage } from "~/hooks/use-onboarding"
import { useOpenSession } from "~/hooks/use-open-session"
import { beneficiaryName, invalidateBeneficiaries } from "~/lib/beneficiaries"

/** Change a beneficiary's payout currency or relationship. The person is
 * fixed: a different person is a different beneficiary. */
export function EditBeneficiaryDialog({
  beneficiary,
  open,
  onOpenChange,
}: {
  beneficiary: BeneficiaryRead
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  // A fresh form, from the current values, every time it opens.
  const session = useOpenSession(open)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <EditBeneficiaryForm
          key={session}
          beneficiary={beneficiary}
          onSaved={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}

function EditBeneficiaryForm({
  beneficiary,
  onSaved,
}: {
  beneficiary: BeneficiaryRead
  onSaved: () => void
}) {
  const queryClient = useQueryClient()
  const name = beneficiaryName(beneficiary)
  const [payoutCurrency, setPayoutCurrency] = useState<PayoutCurrency>(
    beneficiary.payout_currency
  )
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
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (!dirty) return
        update.mutate({
          path: { beneficiary_id: beneficiary.beneficiary_id },
          body: changed,
        })
      }}
    >
      <DialogHeader>
        <DialogTitle>Edit beneficiary</DialogTitle>
        <DialogDescription>
          Change how {name} is paid, or how you know them.
        </DialogDescription>
      </DialogHeader>
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
          id="edit-beneficiary-payout-currency"
          value={payoutCurrency}
          onChange={setPayoutCurrency}
        />
        <RelationshipField
          id="edit-beneficiary-relationship"
          value={relationship}
          onChange={setRelationship}
        />
      </FieldGroup>
      {update.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(update.error)}</AlertDescription>
        </Alert>
      ) : null}
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" />}>
          Cancel
        </DialogClose>
        <Button type="submit" disabled={!dirty || update.isPending}>
          {update.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  )
}
