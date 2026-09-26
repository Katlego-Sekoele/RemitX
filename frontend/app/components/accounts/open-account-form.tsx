import { PlusIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
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
import { cn } from "~/lib/utils"

const CAN_DO = [
  "Receive transfers paid out in that currency",
  "Share its reference so senders can add you and pay you in it",
]

const CANNOT_DO = [
  "Top up by EFT (deposits are ZAR only)",
  "Send money from it",
  "Withdraw to a bank account",
]

/**
 * A dashed placeholder in the accounts grid. Clicking it expands the same
 * card into the open-account form — no header button and no dialog.
 */
export function OpenAccountCard({
  verified,
  heldCurrencies,
}: {
  verified: boolean
  heldCurrencies: readonly string[]
}) {
  const [active, setActive] = useState(false)
  const options = useMemo(
    () => openablePayoutCurrencies(heldCurrencies),
    [heldCurrencies]
  )

  if (verified && options.length === 0) {
    return null
  }

  if (!active) {
    return (
      <Card
        className={cn(
          "ring-dashed min-h-64 justify-center bg-transparent ring-foreground/20"
        )}
      >
        <button
          type="button"
          className="flex min-h-64 flex-col items-stretch text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          onClick={() => setActive(true)}
        >
          <CardHeader>
            <CardTitle>Open account</CardTitle>
            <CardDescription>
              {verified
                ? "Add a payout currency you do not hold yet."
                : "Verify your identity to open accounts in other currencies."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col items-center justify-center gap-2 py-8 text-muted-foreground">
            <PlusIcon className="size-8" aria-hidden="true" />
            <span className="text-sm">
              {verified ? "Choose a currency" : "Verify to continue"}
            </span>
          </CardContent>
        </button>
      </Card>
    )
  }

  return (
    <OpenAccountCardForm
      verified={verified}
      heldCurrencies={heldCurrencies}
      onCancel={() => setActive(false)}
      onOpened={() => setActive(false)}
    />
  )
}

function OpenAccountCardForm({
  verified,
  heldCurrencies,
  onCancel,
  onOpened,
}: {
  verified: boolean
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

  if (!verified) {
    return (
      <Card className="ring-dashed min-h-64 ring-foreground/20">
        <CardHeader>
          <CardTitle>Verification required</CardTitle>
          <CardDescription>
            Only verified customers can open a currency account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            <Link
              to={verificationPath()}
              className="underline underline-offset-4"
            >
              Finish verification
            </Link>{" "}
            to choose a payout currency and get a reference to share.
          </p>
        </CardContent>
        <CardFooter className="justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            Close
          </Button>
        </CardFooter>
      </Card>
    )
  }

  return (
    <Card className="ring-dashed min-h-64 ring-foreground/20">
      <form
        noValidate
        className="flex flex-col gap-(--card-spacing)"
        onSubmit={(event) => {
          event.preventDefault()
          if (!currency) return
          openAccount.mutate({ body: { currency } })
        }}
      >
        <CardHeader>
          <CardTitle>Open account</CardTitle>
          <CardDescription>
            Choose a payout currency. You get a reference to share straight
            away.
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
          <Button type="submit" disabled={!currency || openAccount.isPending}>
            {openAccount.isPending ? "Opening…" : "Open"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
