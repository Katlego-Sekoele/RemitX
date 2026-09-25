import { ArrowLeftIcon, PlusIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState, type ReactNode } from "react"
import { toast } from "sonner"

import {
  api,
  sdk,
  type BeneficiaryLookupResponse,
  type BeneficiaryRead,
  type BeneficiaryRelationship,
  type PayoutCurrency,
} from "~/client"
import {
  asPayoutCurrency,
  PayoutCurrencyField,
  RelationshipField,
} from "~/components/beneficiaries/beneficiary-fields"
import { BeneficiaryAvatar } from "~/components/beneficiaries/beneficiary-avatar"
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
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { errorMessage } from "~/hooks/use-onboarding"
import { invalidateBeneficiaries } from "~/lib/beneficiaries"

type Found = BeneficiaryLookupResponse

/** The **Add beneficiary** button. The form it reveals lives on the page. */
export function AddBeneficiaryButton({
  label = "Add beneficiary",
  variant,
  disabled,
  onClick,
}: {
  label?: ReactNode
  variant?: "default" | "outline" | "secondary" | "ghost"
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <Button variant={variant} disabled={disabled} onClick={onClick}>
      <PlusIcon data-icon="inline-start" />
      {label}
    </Button>
  )
}

/**
 * Add a beneficiary in two steps, on the page: find them by the account
 * reference they gave you, then confirm who it is and choose how they're
 * paid.
 *
 * A modal is only for a final action. Finding someone and choosing how
 * they're paid can be cancelled or changed, so this stays beside the list.
 * `onAdded` receives the new beneficiary, so a caller such as the send flow
 * can select it.
 */
export function AddBeneficiaryForm({
  onCancel,
  onAdded,
}: {
  onCancel: () => void
  onAdded?: (beneficiary: BeneficiaryRead) => void
}) {
  const [found, setFound] = useState<Found | null>(null)

  return found ? (
    <ConfirmStep
      found={found}
      onBack={() => setFound(null)}
      onCancel={onCancel}
      onAdded={onAdded}
    />
  ) : (
    <FindStep onFound={setFound} onCancel={onCancel} />
  )
}

function FindStep({
  onFound,
  onCancel,
}: {
  onFound: (found: Found) => void
  onCancel: () => void
}) {
  const [reference, setReference] = useState("")
  const lookup = useMutation({
    mutationFn: async (accountReference: string) => {
      const { data } = await sdk.beneficiaries.lookupBeneficiaryByReference({
        query: { account_reference: accountReference },
        throwOnError: true,
      })
      return data
    },
    onSuccess: onFound,
  })
  const trimmed = reference.trim()

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        if (trimmed) lookup.mutate(trimmed)
      }}
    >
      <Card>
        <CardHeader>
          <CardTitle>Add beneficiary</CardTitle>
          <CardDescription>
            Find someone by the account reference they gave you.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Field data-invalid={lookup.isError}>
            <FieldLabel htmlFor="beneficiary-reference">
              Account reference
            </FieldLabel>
            <Input
              id="beneficiary-reference"
              value={reference}
              onChange={(event) => {
                setReference(event.target.value)
                if (lookup.isError) lookup.reset()
              }}
              placeholder="tendai1-zwl"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              autoFocus
              aria-invalid={lookup.isError}
            />
            {lookup.isError ? (
              <FieldError>{errorMessage(lookup.error)}</FieldError>
            ) : (
              <FieldDescription>
                Ask them for the reference on their Accounts page, e.g.
                tendai1-zwl.
              </FieldDescription>
            )}
          </Field>
        </CardContent>
        <CardFooter className="flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={lookup.isPending}
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={!trimmed || lookup.isPending}>
            {lookup.isPending ? "Finding…" : "Find"}
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}

function initialPayoutCurrency(found: Found): PayoutCurrency | null {
  const held = found.payout_currencies
  const lookedUp = asPayoutCurrency(found.account_currency)
  if (lookedUp && held.includes(lookedUp)) return lookedUp
  return held.length === 1 ? held[0] : null
}

/**
 * The second step: who the reference belongs to, and how they're paid.
 * Exported so Storybook can show it without a lookup.
 */
export function ConfirmStep({
  found,
  onBack,
  onCancel,
  onAdded,
}: {
  found: Found
  onBack: () => void
  onCancel: () => void
  onAdded?: (beneficiary: BeneficiaryRead) => void
}) {
  const queryClient = useQueryClient()
  const [payoutCurrency, setPayoutCurrency] = useState<PayoutCurrency | null>(
    () => initialPayoutCurrency(found)
  )
  const [relationship, setRelationship] =
    useState<BeneficiaryRelationship | null>(null)
  const create = useMutation({
    ...api.beneficiaries.createBeneficiary(),
    onSuccess: async (beneficiary) => {
      await invalidateBeneficiaries(queryClient)
      toast.success(`${found.display_name ?? "Beneficiary"} added`)
      onAdded?.(beneficiary)
    },
  })
  const who = [found.display_name ?? "Unnamed recipient", found.country_name]
    .filter(Boolean)
    .join(" · ")

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        if (!payoutCurrency || !relationship) return
        create.mutate({
          body: {
            linked_user_id: found.linked_user_id,
            payout_currency: payoutCurrency,
            relationship,
          },
        })
      }}
    >
      <Card>
        <CardHeader>
          <CardTitle>Add beneficiary</CardTitle>
          <CardDescription>
            Check this is who you meant, then choose how they&apos;re paid.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Item variant="muted">
            <ItemMedia>
              <BeneficiaryAvatar
                beneficiary={{
                  full_name: found.display_name ?? found.first_name,
                  profile_image_url: found.profile_image_url,
                }}
              />
            </ItemMedia>
            <ItemContent>
              <ItemTitle>{who}</ItemTitle>
              {found.country_name ? null : (
                <ItemDescription>Not verified yet</ItemDescription>
              )}
            </ItemContent>
          </Item>
          <FieldGroup>
            <PayoutCurrencyField
              id="beneficiary-payout-currency"
              value={payoutCurrency}
              options={found.payout_currencies}
              onChange={setPayoutCurrency}
            />
            <RelationshipField
              id="beneficiary-relationship"
              value={relationship}
              onChange={setRelationship}
            />
          </FieldGroup>
          {create.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(create.error)}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
        <CardFooter className="flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={create.isPending}
            onClick={onBack}
          >
            <ArrowLeftIcon data-icon="inline-start" />
            Back
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={create.isPending}
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={!payoutCurrency || !relationship || create.isPending}
          >
            {create.isPending ? "Saving…" : "Save"}
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}
