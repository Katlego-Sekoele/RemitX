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
import { Alert, AlertDescription } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog"
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
  ItemTitle,
} from "~/components/ui/item"
import { errorMessage } from "~/hooks/use-onboarding"
import { useOpenSession } from "~/hooks/use-open-session"
import { invalidateBeneficiaries } from "~/lib/beneficiaries"

type Found = BeneficiaryLookupResponse

/** The **Add beneficiary** button and the dialog it opens. */
export function AddBeneficiaryButton({
  label = "Add beneficiary",
  variant,
  onAdded,
}: {
  label?: ReactNode
  variant?: "default" | "outline" | "secondary" | "ghost"
  onAdded?: (beneficiary: BeneficiaryRead) => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button variant={variant} onClick={() => setOpen(true)}>
        <PlusIcon data-icon="inline-start" />
        {label}
      </Button>
      <AddBeneficiaryDialog
        open={open}
        onOpenChange={setOpen}
        onAdded={onAdded}
      />
    </>
  )
}

/**
 * Add a beneficiary in two steps: find them by the account reference they
 * gave you, then confirm who it is and choose how they're paid.
 *
 * Controlled, so a caller can open it from its own control, like the send
 * flow's **Add new**. `onAdded` receives the new beneficiary, so that caller
 * can select it.
 */
export function AddBeneficiaryDialog({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onAdded?: (beneficiary: BeneficiaryRead) => void
}) {
  const session = useOpenSession(open)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <AddBeneficiaryFlow
          key={session}
          onAdded={(beneficiary) => {
            onOpenChange(false)
            onAdded?.(beneficiary)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function AddBeneficiaryFlow({
  onAdded,
}: {
  onAdded: (beneficiary: BeneficiaryRead) => void
}) {
  const [found, setFound] = useState<Found | null>(null)

  return found ? (
    <ConfirmStep
      found={found}
      onBack={() => setFound(null)}
      onAdded={onAdded}
    />
  ) : (
    <FindStep onFound={setFound} />
  )
}

function FindStep({ onFound }: { onFound: (found: Found) => void }) {
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
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (trimmed) lookup.mutate(trimmed)
      }}
    >
      <DialogHeader>
        <DialogTitle>Add beneficiary</DialogTitle>
        <DialogDescription>
          Find someone by the account reference they gave you.
        </DialogDescription>
      </DialogHeader>
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
            Ask them for the reference on their Accounts page, e.g. tendai1-zwl.
          </FieldDescription>
        )}
      </Field>
      <DialogFooter>
        <Button type="submit" disabled={!trimmed || lookup.isPending}>
          {lookup.isPending ? "Finding…" : "Find"}
        </Button>
      </DialogFooter>
    </form>
  )
}

function ConfirmStep({
  found,
  onBack,
  onAdded,
}: {
  found: Found
  onBack: () => void
  onAdded: (beneficiary: BeneficiaryRead) => void
}) {
  const queryClient = useQueryClient()
  const [payoutCurrency, setPayoutCurrency] = useState<PayoutCurrency | null>(
    asPayoutCurrency(found.account_currency)
  )
  const [relationship, setRelationship] =
    useState<BeneficiaryRelationship | null>(null)
  const create = useMutation({
    ...api.beneficiaries.createBeneficiary(),
    onSuccess: async (beneficiary) => {
      await invalidateBeneficiaries(queryClient)
      toast.success(`${found.display_name ?? "Beneficiary"} added`)
      onAdded(beneficiary)
    },
  })
  const who = [found.display_name ?? "Unnamed recipient", found.country_name]
    .filter(Boolean)
    .join(" · ")

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
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
      <DialogHeader>
        <DialogTitle>Add beneficiary</DialogTitle>
        <DialogDescription>
          Check this is who you meant, then choose how they&apos;re paid.
        </DialogDescription>
      </DialogHeader>
      <Item variant="muted">
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
      <DialogFooter>
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
          type="submit"
          disabled={!payoutCurrency || !relationship || create.isPending}
        >
          {create.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  )
}
