import { PlusIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState, type ComponentProps, type ReactNode } from "react"
import { toast } from "sonner"

import { api, PayoutCurrency } from "~/client"
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { errorMessage } from "~/hooks/use-onboarding"
import { currencyName } from "~/lib/money"
import { invalidateBankAccounts } from "~/lib/withdrawals"

// The fiat currencies RemitX pays out in. The API refuses anything else.
const CURRENCY_ITEMS = Object.values(PayoutCurrency).map((value) => ({
  value,
  label: `${value} · ${currencyName(value)}`,
}))

type Draft = {
  holder: string
  bank: string
  number: string
  branch: string
  currency: PayoutCurrency | null
}

const EMPTY: Draft = {
  holder: "",
  bank: "",
  number: "",
  branch: "",
  currency: null,
}

/** The **Add bank account** button. The form it reveals lives on the page. */
export function AddBankAccountButton({
  label = "Add bank account",
  disabled,
  onClick,
}: {
  label?: ReactNode
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <Button disabled={disabled} onClick={onClick}>
      <PlusIcon data-icon="inline-start" />
      {label}
    </Button>
  )
}

/**
 * Add a bank account to withdraw into. It starts out awaiting verification:
 * staff check it before any money can be sent there. Nothing here is final,
 * so the form sits on the page rather than in a modal.
 */
export function AddBankAccountForm({
  defaultCurrency,
  onCancel,
  onAdded,
}: {
  defaultCurrency?: PayoutCurrency | null
  onCancel: () => void
  onAdded: () => void
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Draft>({
    ...EMPTY,
    currency: defaultCurrency ?? null,
  })
  const [submitted, setSubmitted] = useState(false)
  const add = useMutation({
    ...api.bank_accounts.addBankAccount(),
    onSuccess: async (account) => {
      await invalidateBankAccounts(queryClient)
      toast.success(`${account.bank_name} account added`, {
        description: "We'll verify it before you can withdraw into it.",
      })
      onAdded()
    },
  })

  const set = (field: keyof Draft) => (value: string) => {
    setDraft((current) => ({ ...current, [field]: value }))
    if (add.isError) add.reset()
  }

  // Blank or whitespace-only text is refused by the API too (422).
  const missing = {
    holder: !draft.holder.trim(),
    bank: !draft.bank.trim(),
    number: !draft.number.trim(),
    currency: draft.currency === null,
  }
  const invalid = Object.values(missing).some(Boolean)
  const show = (field: keyof typeof missing) => submitted && missing[field]

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        setSubmitted(true)
        if (invalid || draft.currency === null) return
        add.mutate({
          body: {
            account_holder_name: draft.holder.trim(),
            bank_name: draft.bank.trim(),
            account_number: draft.number.trim(),
            branch_code: draft.branch.trim() || null,
            currency: draft.currency,
          },
        })
      }}
    >
      <Card>
        <CardHeader>
          <CardTitle>Add bank account</CardTitle>
          <CardDescription>
            An account in your name that we can pay a withdrawal into.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <FieldGroup>
            <TextField
              id="bank-account-holder"
              label="Account holder"
              value={draft.holder}
              onChange={set("holder")}
              autoComplete="name"
              error={show("holder") ? "Enter the account holder." : null}
              autoFocus
            />
            <TextField
              id="bank-account-bank"
              label="Bank"
              value={draft.bank}
              onChange={set("bank")}
              placeholder="FNB"
              error={show("bank") ? "Enter the bank's name." : null}
            />
            <TextField
              id="bank-account-number"
              label="Account number"
              value={draft.number}
              onChange={set("number")}
              inputMode="numeric"
              autoComplete="off"
              error={show("number") ? "Enter the account number." : null}
            />
            <TextField
              id="bank-account-branch"
              label="Branch code"
              value={draft.branch}
              onChange={set("branch")}
              inputMode="numeric"
              autoComplete="off"
              description="Optional."
            />
            <Field data-invalid={show("currency")}>
              <FieldLabel htmlFor="bank-account-currency">Currency</FieldLabel>
              <Select
                items={CURRENCY_ITEMS}
                value={draft.currency}
                onValueChange={(next) => {
                  if (next) set("currency")(next)
                }}
              >
                <SelectTrigger
                  id="bank-account-currency"
                  className="w-full"
                  aria-invalid={show("currency")}
                >
                  <SelectValue placeholder="Choose a currency" />
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {CURRENCY_ITEMS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {show("currency") ? (
                <FieldError>Choose the account&apos;s currency.</FieldError>
              ) : (
                <FieldDescription>
                  You can withdraw into it from your account in this currency.
                </FieldDescription>
              )}
            </Field>
          </FieldGroup>
          {add.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(add.error)}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
        <CardFooter className="flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={add.isPending}
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={add.isPending}>
            {add.isPending ? "Saving…" : "Save"}
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}

function TextField({
  id,
  label,
  value,
  onChange,
  error,
  description,
  ...input
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  error?: string | null
  description?: string
} & Omit<
  ComponentProps<typeof Input>,
  "id" | "value" | "onChange" | "aria-invalid"
>) {
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        {...input}
      />
      {error ? (
        <FieldError>{error}</FieldError>
      ) : description ? (
        <FieldDescription>{description}</FieldDescription>
      ) : null}
    </Field>
  )
}
