import { PlusIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import { api, PayoutCurrency } from "~/client"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { errorMessage } from "~/hooks/use-onboarding"
import { invalidateAccounts, openablePayoutCurrencies } from "~/lib/accounts"
import { verificationPath } from "~/lib/kyc-onboarding"
import { currencyName } from "~/lib/money"

const CAN_DO = [
  "Receive transfers paid out in that currency",
  "Share its reference so senders can add you and pay you in it",
]

const CANNOT_DO = [
  "Top up by EFT (deposits are ZAR only)",
  "Send money from it",
  "Withdraw to a bank account",
]

export function OpenAccountButton({
  label = "Open account",
  variant,
  disabled,
  title,
  onClick,
}: {
  label?: ReactNode
  variant?: "default" | "outline" | "secondary" | "ghost"
  disabled?: boolean
  title?: string
  onClick: () => void
}) {
  return (
    <Button
      variant={variant ?? "outline"}
      disabled={disabled}
      aria-disabled={disabled}
      title={title}
      onClick={onClick}
    >
      <PlusIcon data-icon="inline-start" />
      {label}
    </Button>
  )
}

/** Open a payout account on the page — same pattern as adding a beneficiary. */
export function OpenAccountForm({
  heldCurrencies,
  onCancel,
  onOpened,
}: {
  heldCurrencies: readonly string[]
  onCancel: () => void
  onOpened?: () => void
}) {
  const queryClient = useQueryClient()
  const options = useMemo(
    () => openablePayoutCurrencies(heldCurrencies),
    [heldCurrencies]
  )
  const [currency, setCurrency] = useState<PayoutCurrency | null>(
    options[0] ?? null
  )

  useEffect(() => {
    setCurrency(options[0] ?? null)
  }, [options])

  const openAccount = useMutation({
    ...api.accounts.openAccount(),
    onSuccess: async (account) => {
      await invalidateAccounts(queryClient)
      toast.success(`${currencyName(account.currency)} account opened`)
      onOpened?.()
    },
  })

  const items = options.map((value) => ({
    value,
    label: currencyName(value),
  }))

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        if (!currency) return
        openAccount.mutate({ body: { currency } })
      }}
    >
      <Card>
        <CardHeader>
          <CardTitle>Open a currency account</CardTitle>
          <CardDescription>
            Choose a payout currency you do not hold yet. You get a reference
            to share straight away.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Field data-invalid={openAccount.isError}>
            <FieldLabel htmlFor="open-account-currency">Currency</FieldLabel>
            <Select
              items={items}
              value={currency}
              onValueChange={(next) => {
                if (next) setCurrency(next as PayoutCurrency)
              }}
            >
              <SelectTrigger id="open-account-currency" className="w-full">
                <SelectValue placeholder="Choose a currency" />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {items.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {openAccount.isError ? (
              <FieldError>{errorMessage(openAccount.error)}</FieldError>
            ) : null}
          </Field>

          <div className="grid gap-3 text-sm">
            <div>
              <p className="font-medium">This account can</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
                {CAN_DO.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium">This account cannot yet</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
                {CANNOT_DO.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          </div>
        </CardContent>
        <CardFooter className="flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={openAccount.isPending}
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={!currency || openAccount.isPending}
          >
            {openAccount.isPending ? "Opening…" : "Open"}
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}

export function OpenAccountHeaderAction({
  verified,
  heldCurrencies,
  opening,
  onOpen,
}: {
  verified: boolean
  heldCurrencies: readonly string[]
  opening: boolean
  onOpen: () => void
}) {
  const options = openablePayoutCurrencies(heldCurrencies)
  const disabled = !verified || options.length === 0 || opening
  const title = !verified
    ? "Finish verification to open another currency account."
    : options.length === 0
      ? "You already hold every payout currency."
      : undefined

  return (
    <div className="flex max-w-sm flex-col items-end gap-2">
      <OpenAccountButton
        disabled={disabled}
        title={title}
        onClick={onOpen}
      />
      {!verified ? (
        <p className="text-sm text-muted-foreground">
          <Link to={verificationPath()} className="underline underline-offset-4">
            Verify your identity
          </Link>{" "}
          to open accounts in other currencies.
        </p>
      ) : null}
    </div>
  )
}
