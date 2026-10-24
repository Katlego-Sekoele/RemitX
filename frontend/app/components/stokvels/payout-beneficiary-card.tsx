import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import { api, type BeneficiaryRead } from "~/client"
import { AddBeneficiaryForm } from "~/components/beneficiaries/add-beneficiary-form"
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
import { currencyName } from "~/lib/money"
import { stokvelErrorMessage } from "~/lib/stokvel-errors"
import {
  invalidateStokvels,
  stokvelMutations,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/** The app's beneficiaries page, where a payout currency is changed. */
const BENEFICIARIES_HREF = "/app/beneficiaries"

/**
 * Who the member's payout goes to this cycle (R4-06, #255): one of their
 * existing beneficiaries, paid in that beneficiary's saved payout currency
 * (`PUT /stokvels/{id}/members/me/beneficiary`, #231). A new beneficiary is
 * added with the app's own form, not a copy of it (brief §7.3). Every member
 * must choose before the cycle can start, and the choice locks when it does.
 */
export function PayoutBeneficiaryCard({
  stokvel,
}: {
  stokvel: StokvelDetailRead
}) {
  const queryClient = useQueryClient()
  const beneficiaries = useQuery(api.beneficiaries.listMyBeneficiaries())
  const current = stokvel.my_beneficiary
  const [editing, setEditing] = useState(current === null)
  const [adding, setAdding] = useState(false)
  const [beneficiaryId, setBeneficiaryId] = useState(
    current?.beneficiary_id ?? ""
  )

  const save = useMutation({
    ...stokvelMutations.setMyBeneficiary(stokvel.stokvel_id),
    onSuccess: async (_, beneficiary) => {
      setEditing(false)
      await invalidateStokvels(queryClient)
      toast.success(`Your payout goes to ${beneficiaryName(beneficiary)}`)
    },
  })

  const list = beneficiaries.data ?? []
  const chosen = list.find((b) => b.beneficiary_id === beneficiaryId)

  if (adding) {
    return (
      <AddBeneficiaryForm
        onCancel={() => setAdding(false)}
        onAdded={(beneficiary: BeneficiaryRead) => {
          setBeneficiaryId(beneficiary.beneficiary_id)
          setAdding(false)
        }}
      />
    )
  }

  if (!editing && current) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle>Your payout</CardTitle>
            <Badge>Ready</Badge>
          </div>
          <CardDescription>
            When it&apos;s your round, the pool goes to{" "}
            {current.full_name ?? "your beneficiary"} in{" "}
            {current.payout_currency}. You can change this until the cycle
            starts.
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            Change
          </Button>
        </CardFooter>
      </Card>
    )
  }

  const items = list.map((b) => ({
    value: b.beneficiary_id,
    label: `${beneficiaryName(b)} · ${b.payout_currency}`,
  }))

  return (
    <Card>
      <form
        noValidate
        className="flex flex-col gap-(--card-spacing)"
        onSubmit={(event) => {
          event.preventDefault()
          if (chosen) save.mutate(chosen)
        }}
      >
        <CardHeader>
          <CardTitle>Your payout</CardTitle>
          <CardDescription>
            Choose who receives the pool in your round. It is sent to them
            directly, like a transfer from the stokvel.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {beneficiaries.isPending ? (
            <Skeleton className="h-16 w-full" />
          ) : beneficiaries.isError ? (
            <FieldError>{errorMessage(beneficiaries.error)}</FieldError>
          ) : (
            <FieldGroup>
              {list.length > 0 ? (
                <Field>
                  <FieldLabel htmlFor="payout-beneficiary">
                    Beneficiary
                  </FieldLabel>
                  <Select
                    items={items}
                    value={beneficiaryId || null}
                    onValueChange={(next) => setBeneficiaryId(next ?? "")}
                  >
                    <SelectTrigger id="payout-beneficiary" className="w-full">
                      <SelectValue placeholder="Choose a beneficiary" />
                    </SelectTrigger>
                    <SelectContent alignItemWithTrigger={false}>
                      {items.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {chosen ? (
                    <FieldDescription>
                      Paid in {chosen.payout_currency} (
                      {currencyName(chosen.payout_currency)}), their saved
                      payout currency. To change it, edit them on the{" "}
                      <Link to={BENEFICIARIES_HREF} className="underline">
                        Beneficiaries
                      </Link>{" "}
                      page.
                    </FieldDescription>
                  ) : null}
                </Field>
              ) : (
                <FieldDescription>
                  You have no beneficiaries yet. Add the person who should
                  receive your payout.
                </FieldDescription>
              )}
              {save.isError ? (
                <FieldError>{stokvelErrorMessage(save.error)}</FieldError>
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
          <div className="flex gap-2">
            {current ? (
              <Button
                type="button"
                variant="ghost"
                disabled={save.isPending}
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
            ) : null}
            <Button type="submit" disabled={!chosen || save.isPending}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </CardFooter>
      </form>
    </Card>
  )
}
