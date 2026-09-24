import { PlusIcon, UsersThreeIcon } from "@phosphor-icons/react"
import { useState } from "react"

import type { BeneficiaryRead as Beneficiary } from "~/client"
import { AddBeneficiaryForm } from "~/components/beneficiaries/add-beneficiary-form"
import { BeneficiaryAvatar } from "~/components/beneficiaries/beneficiary-avatar"
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
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "~/components/ui/combobox"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { Skeleton } from "~/components/ui/skeleton"
import { useKycReferenceQuery } from "~/hooks/use-kyc-reference"
import { errorMessage } from "~/hooks/use-onboarding"
import { beneficiaryName } from "~/lib/beneficiaries"
import { countryName } from "~/lib/kyc-reference"

// Module-level so their identities never change between renders.
const beneficiaryId = (beneficiary: Beneficiary) => beneficiary.beneficiary_id
const sameBeneficiary = (left: Beneficiary, right: Beneficiary) =>
  left.beneficiary_id === right.beneficiary_id

export function RecipientStep({
  beneficiaries,
  loading,
  error,
  selected,
  missing,
  onSelect,
  onContinue,
}: {
  beneficiaries: Beneficiary[]
  loading: boolean
  error: unknown
  selected: Beneficiary | null
  /** The URL named a beneficiary that isn't one of the caller's. */
  missing: boolean
  onSelect: (beneficiary: Beneficiary | null) => void
  onContinue: () => void
}) {
  const [adding, setAdding] = useState(false)
  const reference = useKycReferenceQuery()

  const describe = (beneficiary: Beneficiary) =>
    `${countryName(reference.data, beneficiary.country)} · paid in ${beneficiary.payout_currency}`

  const matches = (beneficiary: Beneficiary, query: string) => {
    const needle = query.trim().toLowerCase()
    return (
      needle === "" ||
      beneficiaryName(beneficiary).toLowerCase().includes(needle) ||
      describe(beneficiary).toLowerCase().includes(needle)
    )
  }

  if (loading) {
    return <Skeleton className="h-40 w-full" />
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Who are you sending to?</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldError>{errorMessage(error)}</FieldError>
        </CardContent>
      </Card>
    )
  }

  if (adding) {
    return (
      <AddBeneficiaryForm
        onCancel={() => setAdding(false)}
        onAdded={(beneficiary) => {
          onSelect(beneficiary)
          setAdding(false)
        }}
      />
    )
  }

  if (beneficiaries.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <UsersThreeIcon />
          </EmptyMedia>
          <EmptyTitle>No beneficiaries yet</EmptyTitle>
          <EmptyDescription>
            Add the person you&apos;re sending to. You&apos;ll need the account
            reference they shared with you.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button onClick={() => setAdding(true)}>
            <PlusIcon />
            Add beneficiary
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Who are you sending to?</CardTitle>
        <CardDescription>
          Pick one of your beneficiaries, or add someone new.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Field data-invalid={missing}>
          <FieldLabel htmlFor="send-recipient">Recipient</FieldLabel>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Combobox
              items={beneficiaries}
              value={selected}
              onValueChange={(next) => onSelect(next)}
              itemToStringLabel={beneficiaryName}
              itemToStringValue={beneficiaryId}
              isItemEqualToValue={sameBeneficiary}
              filter={matches}
              autoHighlight
            >
              <ComboboxInput
                id="send-recipient"
                className="w-full sm:flex-1"
                placeholder="Search your beneficiaries"
                aria-invalid={missing}
              />
              <ComboboxContent>
                <ComboboxEmpty>No beneficiary matches that.</ComboboxEmpty>
                <ComboboxList>
                  {(beneficiary: Beneficiary) => (
                    <ComboboxItem
                      key={beneficiary.beneficiary_id}
                      value={beneficiary}
                    >
                      <Item size="xs" className="p-0">
                        <ItemMedia>
                          <BeneficiaryAvatar
                            beneficiary={beneficiary}
                            size="sm"
                          />
                        </ItemMedia>
                        <ItemContent>
                          <ItemTitle>{beneficiaryName(beneficiary)}</ItemTitle>
                          <ItemDescription>
                            {describe(beneficiary)}
                          </ItemDescription>
                        </ItemContent>
                      </Item>
                    </ComboboxItem>
                  )}
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
            <Button variant="outline" onClick={() => setAdding(true)}>
              <PlusIcon />
              Add new
            </Button>
          </div>
          {missing ? (
            <FieldError>
              That beneficiary isn&apos;t in your list. Pick someone else.
            </FieldError>
          ) : null}
        </Field>
        {selected ? (
          <Item variant="outline">
            <ItemMedia>
              <BeneficiaryAvatar beneficiary={selected} />
            </ItemMedia>
            <ItemContent>
              <ItemTitle>{beneficiaryName(selected)}</ItemTitle>
              <ItemDescription>{describe(selected)}</ItemDescription>
            </ItemContent>
          </Item>
        ) : null}
      </CardContent>
      <CardFooter className="justify-end">
        <Button disabled={!selected} onClick={onContinue}>
          Continue
        </Button>
      </CardFooter>
    </Card>
  )
}
