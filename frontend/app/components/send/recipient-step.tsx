import { CheckIcon, PlusIcon, UsersThreeIcon } from "@phosphor-icons/react"
import { useState } from "react"

import type { BeneficiaryRead as Beneficiary } from "~/client"
import { AddBeneficiaryForm } from "~/components/beneficiaries/add-beneficiary-form"
import { Avatar, AvatarBadge, AvatarFallback } from "~/components/ui/avatar"
import { Button } from "~/components/ui/button"
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
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "~/components/ui/field"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "~/components/ui/item"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip"
import { useKycReferenceQuery } from "~/hooks/use-kyc-reference"
import { errorMessage } from "~/hooks/use-onboarding"
import {
  beneficiaryInitials,
  beneficiaryName,
  quickPicks,
} from "~/lib/beneficiaries"
import { countryName } from "~/lib/kyc-reference"

/** How many beneficiaries the avatar row offers before search takes over. */
const QUICK_PICKS = 6

// Module-level so their identities never change between renders.
const beneficiaryId = (beneficiary: Beneficiary) => beneficiary.beneficiary_id
const sameBeneficiary = (left: Beneficiary, right: Beneficiary) =>
  left.beneficiary_id === right.beneficiary_id

/** A beneficiary's avatar: initials, as on the Beneficiaries page, until
 * the API carries a profile photo. */
export function BeneficiaryAvatar({
  beneficiary,
  size = "default",
  selected = false,
}: {
  beneficiary: Beneficiary
  size?: "default" | "sm" | "lg"
  selected?: boolean
}) {
  return (
    <Avatar size={size}>
      <AvatarFallback>{beneficiaryInitials(beneficiary)}</AvatarFallback>
      {selected ? (
        <AvatarBadge>
          <CheckIcon weight="bold" />
        </AvatarBadge>
      ) : null}
    </Avatar>
  )
}

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
    return <FieldError>{errorMessage(error)}</FieldError>
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
    <div className="flex flex-col gap-5">
      <Field data-invalid={missing}>
        <FieldLabel>To</FieldLabel>
        <div
          role="group"
          aria-label="Your beneficiaries"
          className="flex flex-wrap items-center gap-3"
        >
          {quickPicks(
            beneficiaries,
            selected?.beneficiary_id ?? null,
            QUICK_PICKS
          ).map((beneficiary) => {
            const isSelected =
              beneficiary.beneficiary_id === selected?.beneficiary_id
            return (
              <Tooltip key={beneficiary.beneficiary_id}>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon-lg"
                      className="rounded-full"
                      aria-pressed={isSelected}
                      aria-label={beneficiaryName(beneficiary)}
                      onClick={() => onSelect(beneficiary)}
                    />
                  }
                >
                  <BeneficiaryAvatar
                    beneficiary={beneficiary}
                    size="lg"
                    selected={isSelected}
                  />
                </TooltipTrigger>
                <TooltipContent>{beneficiaryName(beneficiary)}</TooltipContent>
              </Tooltip>
            )
          })}
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="outline"
                  size="icon-lg"
                  className="rounded-full"
                  aria-label="Add a beneficiary"
                  onClick={() => setAdding(true)}
                />
              }
            >
              <PlusIcon />
            </TooltipTrigger>
            <TooltipContent>Add a beneficiary</TooltipContent>
          </Tooltip>
        </div>
        {selected ? (
          <FieldDescription>
            Sending to <strong>{beneficiaryName(selected)}</strong> ·{" "}
            {describe(selected)}
          </FieldDescription>
        ) : null}
        {missing ? (
          <FieldError>
            That beneficiary isn&apos;t in your list. Pick someone else.
          </FieldError>
        ) : null}
      </Field>

      <Field>
        <FieldLabel htmlFor="send-recipient">
          Search all your beneficiaries
        </FieldLabel>
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
            className="w-full"
            placeholder="Search by name or country"
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
                    <BeneficiaryAvatar beneficiary={beneficiary} size="sm" />
                    <ItemContent>
                      <ItemTitle>{beneficiaryName(beneficiary)}</ItemTitle>
                      <ItemDescription>{describe(beneficiary)}</ItemDescription>
                    </ItemContent>
                  </Item>
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
      </Field>

      <div className="flex justify-end">
        <Button disabled={!selected} onClick={onContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}
