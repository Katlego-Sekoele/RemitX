import { WarningCircleIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"

import { sdk, type BeneficiaryRead as Beneficiary } from "~/client"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
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
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { Skeleton } from "~/components/ui/skeleton"
import { useDebouncedValue } from "~/hooks/use-debounced-value"
import { errorMessage } from "~/hooks/use-onboarding"
import { beneficiaryName } from "~/lib/beneficiaries"
import { formatMoney, invertRate } from "~/lib/money"
import {
  amountIssue,
  amountIssueMessage,
  canPreview,
  isRatesUnavailable,
  isTooSmallForFees,
  normalizeAmount,
  PAYOUT_CURRENCIES,
  PREVIEW_DEBOUNCE_MS,
  RATES_UNAVAILABLE_MESSAGE,
  sanitizeAmountInput,
  SENDER_CURRENCY,
  type AmountLimits,
  type PayoutCurrency,
} from "~/lib/send"

const CURRENCY_ITEMS = PAYOUT_CURRENCIES.map((currency) => ({
  value: currency,
  label: currency,
}))

/** The indicative price for an amount; nothing is held or saved. */
function usePreview(
  amount: string,
  currency: PayoutCurrency,
  enabled: boolean
) {
  const senderAmount = normalizeAmount(amount)
  return useQuery({
    queryKey: ["quotes", "preview", senderAmount, currency],
    queryFn: async ({ signal }) => {
      const { data } = await sdk.quotes.previewQuote({
        body: {
          sender_amount: senderAmount,
          sender_currency: SENDER_CURRENCY,
          receiver_payout_currency: currency,
        },
        signal,
        throwOnError: true,
      })
      return data
    },
    enabled,
    // Rates move slowly; the same amount typed again reuses the answer.
    staleTime: 30_000,
  })
}

export function AmountStep({
  beneficiary,
  amount,
  currency,
  limits,
  onAmountChange,
  onCurrencyChange,
  onBack,
  onContinue,
}: {
  beneficiary: Beneficiary
  amount: string
  currency: PayoutCurrency
  limits: AmountLimits
  onAmountChange: (amount: string) => void
  onCurrencyChange: (currency: PayoutCurrency) => void
  onBack: () => void
  onContinue: () => void
}) {
  const debounced = useDebouncedValue(amount, PREVIEW_DEBOUNCE_MS)
  const settled = debounced === amount
  const previewable = canPreview(amountIssue(debounced, limits))
  const preview = usePreview(debounced, currency, previewable)

  const issue =
    amountIssue(amount, limits) ??
    (settled && isTooSmallForFees(preview.error) ? "too_small_for_fees" : null)
  const ratesUnavailable = settled && isRatesUnavailable(preview.error)
  const priced = settled && preview.isSuccess && !preview.isFetching
  // An empty field isn't a mistake yet; everything else is said at once.
  const showIssue = issue !== null && issue !== "empty"
  const name = beneficiaryName(beneficiary)

  return (
    <Card>
      <CardHeader>
        <CardTitle>How much are you sending?</CardTitle>
        <CardDescription>To {name}, from your ZAR balance.</CardDescription>
      </CardHeader>
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          if (issue === null && priced) onContinue()
        }}
      >
        <CardContent className="flex flex-col gap-6">
          <FieldGroup>
            <Field data-invalid={showIssue}>
              <FieldLabel htmlFor="send-amount">You send (ZAR)</FieldLabel>
              <InputGroup>
                <InputGroupAddon>
                  <InputGroupText>R</InputGroupText>
                </InputGroupAddon>
                <InputGroupInput
                  id="send-amount"
                  value={amount}
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="0.00"
                  aria-invalid={showIssue}
                  onChange={(event) =>
                    onAmountChange(sanitizeAmountInput(event.target.value))
                  }
                />
              </InputGroup>
              <FieldDescription>
                {limits.available === undefined
                  ? "Loading your balance…"
                  : `Available: ${formatMoney(limits.available, SENDER_CURRENCY)}`}
                {limits.dailyRemaining === undefined
                  ? null
                  : ` · Daily limit: ${formatMoney(limits.dailyRemaining, SENDER_CURRENCY)}`}
                {limits.monthlyRemaining === undefined
                  ? null
                  : ` · Monthly limit: ${formatMoney(limits.monthlyRemaining, SENDER_CURRENCY)}`}
              </FieldDescription>
              {showIssue ? (
                <FieldError>{amountIssueMessage(issue, limits)}</FieldError>
              ) : null}
            </Field>
            <Field>
              <FieldLabel htmlFor="send-currency">They receive in</FieldLabel>
              <Select
                items={CURRENCY_ITEMS}
                value={currency}
                onValueChange={(next) => {
                  if (next) onCurrencyChange(next)
                }}
              >
                <SelectTrigger id="send-currency" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  <SelectGroup>
                    {CURRENCY_ITEMS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <FieldDescription>
                {currency === beneficiary.payout_currency
                  ? `${name}'s payout currency.`
                  : `For this transfer only. ${name} is usually paid in ${beneficiary.payout_currency}.`}
              </FieldDescription>
            </Field>
          </FieldGroup>

          {ratesUnavailable ? (
            <Alert variant="destructive">
              <WarningCircleIcon />
              <AlertTitle>{RATES_UNAVAILABLE_MESSAGE}</AlertTitle>
              <AlertDescription>Try again in a few minutes.</AlertDescription>
            </Alert>
          ) : null}

          {previewable &&
          !ratesUnavailable &&
          !isTooSmallForFees(preview.error) ? (
            <section aria-label="Estimate" className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Badge variant="outline">Estimate</Badge>
                <FieldDescription>
                  The firm price comes with your quote on the next step.
                </FieldDescription>
              </div>
              {preview.isError && settled ? (
                <FieldError>{errorMessage(preview.error)}</FieldError>
              ) : priced && preview.data ? (
                <DescriptionList className="sm:grid-cols-3">
                  <DescriptionItem>
                    <DescriptionTerm>They receive</DescriptionTerm>
                    <DescriptionDetails>
                      ≈{" "}
                      {formatMoney(
                        preview.data.receiver_amount,
                        preview.data.receiver_payout_currency
                      )}
                    </DescriptionDetails>
                  </DescriptionItem>
                  <DescriptionItem>
                    <DescriptionTerm>Exchange rate</DescriptionTerm>
                    <DescriptionDetails>
                      1 USD = R{" "}
                      {invertRate(preview.data.fiat_to_token_exchange_rate)}
                    </DescriptionDetails>
                  </DescriptionItem>
                  <DescriptionItem>
                    <DescriptionTerm>Fees</DescriptionTerm>
                    <DescriptionDetails>
                      {formatMoney(
                        preview.data.sender_transaction_fee,
                        SENDER_CURRENCY
                      )}
                    </DescriptionDetails>
                    <FieldDescription>
                      Plus{" "}
                      {formatMoney(
                        preview.data.exchange_rate_margin,
                        SENDER_CURRENCY
                      )}{" "}
                      FX margin
                    </FieldDescription>
                  </DescriptionItem>
                </DescriptionList>
              ) : (
                <Skeleton className="h-12 w-full" />
              )}
            </section>
          ) : null}
        </CardContent>
        <CardFooter className="justify-between gap-2">
          <Button type="button" variant="outline" onClick={onBack}>
            Back
          </Button>
          <Button type="submit" disabled={issue !== null || !priced}>
            Get quote
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
