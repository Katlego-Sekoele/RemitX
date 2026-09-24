import { ArrowCircleUpIcon } from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useRef, useState } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import {
  api,
  type AccountRead,
  type BankAccountRead,
  type WithdrawalRead,
} from "~/client"
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
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "~/components/ui/input-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { errorMessage } from "~/hooks/use-onboarding"
import { currencyName, formatMoney } from "~/lib/money"
import { sanitizeAmountInput } from "~/lib/send"
import {
  BANK_ACCOUNTS_HREF,
  bankAccountLabel,
  invalidateAfterWithdrawal,
  withdrawalAmountError,
} from "~/lib/withdrawals"

/**
 * Withdraw from one of the customer's fiat accounts into one of their
 * verified bank accounts in the same currency. The cash-out fee comes out of
 * the amount, and the API settles the withdrawal in the same request, so the
 * receipt below the form is final.
 *
 * Final, but not a modal: where from, where to and how much are all on the
 * card beside the button, as they are on Send's review step.
 */
export function WithdrawForm({
  accounts,
  initialCurrency,
}: {
  /** The customer's fiat accounts. */
  accounts: readonly AccountRead[]
  initialCurrency?: string | null
}) {
  const queryClient = useQueryClient()
  const [currency, setCurrency] = useState<string | null>(
    () =>
      accounts.find((account) => account.currency === initialCurrency)
        ?.currency ??
      accounts[0]?.currency ??
      null
  )
  const [bankAccountId, setBankAccountId] = useState<string | null>(null)
  const [amount, setAmount] = useState("")
  const [submitted, setSubmitted] = useState(false)
  const [receipt, setReceipt] = useState<WithdrawalRead | null>(null)

  const account = accounts.find((candidate) => candidate.currency === currency)
  const destinations = useQuery({
    ...api.bank_accounts.listWithdrawableBankAccounts({
      query: { currency: currency ?? "" },
    }),
    enabled: currency !== null,
  })
  const destination = destinations.data?.find(
    (candidate) => candidate.bank_account_id === bankAccountId
  )

  // A second click before the first request settles must not pay out twice.
  const sending = useRef(false)
  const withdraw = useMutation({
    ...api.withdrawals.requestWithdrawal(),
    onSettled: () => {
      sending.current = false
    },
    onSuccess: async (withdrawal) => {
      setReceipt(withdrawal)
      setAmount("")
      setSubmitted(false)
      await invalidateAfterWithdrawal(queryClient)
      toast.success(
        `${formatMoney(withdrawal.net_amount, withdrawal.currency)} is on its way`
      )
    },
  })

  const amountError = account
    ? withdrawalAmountError(amount, account.available_balance)
    : null
  const showAmountError = amountError !== null && (submitted || amount !== "")
  const missingDestination = destination === undefined

  const accountItems = accounts.map((candidate) => ({
    value: candidate.currency,
    label: `${candidate.currency} · ${currencyName(candidate.currency)}`,
  }))

  return (
    <div className="flex flex-col gap-4">
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          setSubmitted(true)
          if (!account || !destination || amountError !== null) return
          if (sending.current) return
          sending.current = true
          withdraw.mutate({
            body: {
              bank_account_id: destination.bank_account_id,
              currency: account.currency,
              amount,
            },
          })
        }}
      >
        <Card>
          <CardHeader>
            <CardTitle>Withdraw to your bank</CardTitle>
            <CardDescription>
              RemitX&apos;s cash-out fee comes out of the amount you withdraw.
              Your receipt shows the fee and what reaches your bank.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="withdraw-account">From</FieldLabel>
                <Select
                  items={accountItems}
                  value={currency}
                  onValueChange={(next) => {
                    if (!next) return
                    setCurrency(next)
                    setBankAccountId(null)
                    setReceipt(null)
                    withdraw.reset()
                  }}
                >
                  <SelectTrigger id="withdraw-account" className="w-full">
                    <SelectValue placeholder="Choose an account" />
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {accountItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {account ? (
                  <FieldDescription>
                    Available:{" "}
                    {formatMoney(account.available_balance, account.currency)}
                  </FieldDescription>
                ) : null}
              </Field>

              <DestinationField
                currency={currency}
                destinations={destinations.data}
                loading={destinations.isPending && currency !== null}
                error={destinations.isError ? destinations.error : null}
                value={bankAccountId}
                onChange={(next) => {
                  setBankAccountId(next)
                  setReceipt(null)
                  withdraw.reset()
                }}
                showMissing={submitted && missingDestination}
              />

              <Field data-invalid={showAmountError}>
                <FieldLabel htmlFor="withdraw-amount">
                  Amount{currency ? ` (${currency})` : ""}
                </FieldLabel>
                <InputGroup>
                  {currency ? (
                    <InputGroupAddon>
                      <InputGroupText>{currency}</InputGroupText>
                    </InputGroupAddon>
                  ) : null}
                  <InputGroupInput
                    id="withdraw-amount"
                    value={amount}
                    type="text"
                    inputMode="decimal"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="0.00"
                    aria-invalid={showAmountError}
                    onChange={(event) => {
                      setAmount(sanitizeAmountInput(event.target.value))
                      setReceipt(null)
                      withdraw.reset()
                    }}
                  />
                </InputGroup>
                {showAmountError ? (
                  <FieldError>{amountError}</FieldError>
                ) : null}
              </Field>
            </FieldGroup>
            {withdraw.isError ? (
              <Alert variant="destructive">
                <AlertDescription>
                  {errorMessage(withdraw.error)}
                </AlertDescription>
              </Alert>
            ) : null}
          </CardContent>
          <CardFooter className="flex-wrap items-center justify-between gap-2">
            <CardDescription>
              Paid out straight away. This can&apos;t be undone.
            </CardDescription>
            <Button type="submit" disabled={!account || withdraw.isPending}>
              <ArrowCircleUpIcon data-icon="inline-start" />
              {withdraw.isPending ? "Withdrawing…" : "Withdraw"}
            </Button>
          </CardFooter>
        </Card>
      </form>

      {receipt ? (
        <WithdrawalReceipt
          withdrawal={receipt}
          destination={destinations.data?.find(
            (candidate) => candidate.bank_account_id === receipt.bank_account_id
          )}
        />
      ) : null}
    </div>
  )
}

function DestinationField({
  currency,
  destinations,
  loading,
  error,
  value,
  onChange,
  showMissing,
}: {
  currency: string | null
  destinations: readonly BankAccountRead[] | undefined
  loading: boolean
  error: unknown
  value: string | null
  onChange: (bankAccountId: string) => void
  showMissing: boolean
}) {
  const items = (destinations ?? []).map((account) => ({
    value: account.bank_account_id,
    label: bankAccountLabel(account),
  }))
  const none = !loading && !error && items.length === 0

  return (
    <Field data-invalid={showMissing && !none}>
      <FieldLabel htmlFor="withdraw-destination">To</FieldLabel>
      <Select
        items={items}
        value={value}
        disabled={loading || none || currency === null}
        onValueChange={(next) => {
          if (next) onChange(next)
        }}
      >
        <SelectTrigger
          id="withdraw-destination"
          className="w-full"
          aria-invalid={showMissing && !none}
        >
          <SelectValue
            placeholder={
              loading ? "Loading your bank accounts…" : "Choose a bank account"
            }
          />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error ? (
        <FieldError>{errorMessage(error)}</FieldError>
      ) : none ? (
        <FieldDescription>
          You have no verified {currency} bank account yet.{" "}
          <Link to={BANK_ACCOUNTS_HREF}>Add one</Link>, and we&apos;ll verify it
          before you can withdraw.
        </FieldDescription>
      ) : showMissing ? (
        <FieldError>Choose the bank account to pay into.</FieldError>
      ) : (
        <FieldDescription>
          Only verified accounts in this currency are listed.
        </FieldDescription>
      )}
    </Field>
  )
}

function WithdrawalReceipt({
  withdrawal,
  destination,
}: {
  withdrawal: WithdrawalRead
  destination?: BankAccountRead
}) {
  const money = (amount: string) => formatMoney(amount, withdrawal.currency)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Withdrawal sent</CardTitle>
        <CardDescription>
          {destination
            ? `Paid to ${bankAccountLabel(destination)}.`
            : "Paid to your bank account."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>You withdrew</DescriptionTerm>
            <DescriptionDetails className="tabular-nums">
              {money(withdrawal.gross_amount)}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Cash-out fee</DescriptionTerm>
            <DescriptionDetails className="tabular-nums">
              {money(withdrawal.fee_amount)}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Reaches your bank</DescriptionTerm>
            <DescriptionDetails className="font-heading text-2xl font-semibold tabular-nums">
              {money(withdrawal.net_amount)}
            </DescriptionDetails>
          </DescriptionItem>
        </DescriptionList>
      </CardContent>
    </Card>
  )
}
