import { PlusIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import { api, PayoutCurrency } from "~/client"
import { Button } from "~/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog"
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

export function OpenAccountDialog({
  open,
  onOpenChange,
  heldCurrencies,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  heldCurrencies: readonly string[]
}) {
  const queryClient = useQueryClient()
  const options = useMemo(
    () => openablePayoutCurrencies(heldCurrencies),
    [heldCurrencies]
  )
  const [currency, setCurrency] = useState<PayoutCurrency | null>(
    options[0] ?? null
  )

  const openAccount = useMutation({
    ...api.accounts.openAccount(),
    onSuccess: async (account) => {
      onOpenChange(false)
      await invalidateAccounts(queryClient)
      toast.success(`${currencyName(account.currency)} account opened`)
    },
  })

  const items = options.map((value) => ({
    value,
    label: currencyName(value),
  }))

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) {
          openAccount.reset()
          setCurrency(options[0] ?? null)
        }
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Open a currency account</DialogTitle>
          <DialogDescription>
            Choose a payout currency you do not hold yet. You get a reference
            to share straight away.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <Field>
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

          {openAccount.isError ? (
            <FieldError>{errorMessage(openAccount.error)}</FieldError>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            disabled={openAccount.isPending}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            disabled={!currency || openAccount.isPending}
            onClick={() => {
              if (!currency) return
              openAccount.mutate({ body: { currency } })
            }}
          >
            {openAccount.isPending ? "Opening…" : "Open"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function OpenAccountButton({
  verified,
  heldCurrencies,
}: {
  verified: boolean
  heldCurrencies: readonly string[]
}) {
  const [open, setOpen] = useState(false)
  const options = openablePayoutCurrencies(heldCurrencies)
  const disabled = !verified || options.length === 0
  const title = !verified
    ? "Finish verification to open another currency account."
    : options.length === 0
      ? "You already hold every payout currency."
      : undefined

  return (
    <>
      <Button
        variant="outline"
        disabled={disabled}
        aria-disabled={disabled}
        title={title}
        onClick={() => setOpen(true)}
      >
        <PlusIcon data-icon="inline-start" />
        Open account
      </Button>
      {!verified ? (
        <p className="text-sm text-muted-foreground">
          <Link to={verificationPath()} className="underline underline-offset-4">
            Verify your identity
          </Link>{" "}
          to open accounts in other currencies.
        </p>
      ) : null}
      {verified && options.length > 0 ? (
        <OpenAccountDialog
          open={open}
          onOpenChange={setOpen}
          heldCurrencies={heldCurrencies}
        />
      ) : null}
    </>
  )
}
