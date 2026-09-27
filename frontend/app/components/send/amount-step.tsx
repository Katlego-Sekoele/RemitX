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
import {
  currencySymbol,
  formatFiatToTokenExchangeRate,
  formatMoney,
} from "~/lib/money"
import {
  amountIssue,
  amountIssueMessage,
  canPreview,
  DEFAULT_SENDER_CURRENCY,
  estimateInCurrency,
  isRatesUnavailable,
  isTooSmallForFees,
  normalizeAmount,
  PREVIEW_DEBOUNCE_MS,
  RATES_UNAVAILABLE_MESSAGE,
  sanitizeAmountInput,
  type AmountLimits,
  type PayoutCurrency,
} from "~/lib/send"

/** The indicative price for an amount; nothing is held or saved. */
function usePreview(
  amount: string,
  fromCurrency: string,
  toCurrency: PayoutCurrency,
  enabled: boolean
) {
  const senderAmount = normalizeAmount(amount)
  return useQuery({
    queryKey: ["quotes", "preview", senderAmount, fromCurrency, toCurrency],
    queryFn: async ({ signal }) => {
      const { data } = await sdk.quotes.previewQuote({
        body: {
          sender_amount: senderAmount,
          sender_currency: fromCurrency,
          receiver_payout_currency: toCurrency,
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

/** One of the sender's fiat accounts, as `send.tsx` reads it off `GET
 * /accounts` (`kind === "fiat"`, the token account excluded). */
export type FromAccount = { currency: string; available_balance: string }

/** "R 800.00 (≈ USD 43.24)", or just the rand figure with no estimate. */
function remainingLine(
  remainingZar: string,
  estimate: { amount: string; currency: string } | undefined
): string {
  const zar = formatMoney(remainingZar, "ZAR")
  return estimate
    ? `${zar} (≈ ${formatMoney(estimate.amount, estimate.currency)})`
    : zar
}

export function AmountStep({
  beneficiary,
  amount,
  currency,
  fromCurrency,
  fromAccounts,
  limits,
  onAmountChange,
  onCurrencyChange,
  onFromChange,
  onBack,
  onContinue,
}: {
  beneficiary: Beneficiary
  amount: string
  currency: PayoutCurrency
  /** Which of `fromAccounts` this send leaves from. */
  fromCurrency: string
  fromAccounts: FromAccount[]
  limits: AmountLimits
  onAmountChange: (amount: string) => void
  onCurrencyChange: (currency: PayoutCurrency) => void
  onFromChange: (currency: string) => void
  onBack: () => void
  onContinue: () => void
}) {
  const debounced = useDebouncedValue(amount, PREVIEW_DEBOUNCE_MS)
  const settled = debounced === amount
  const isZar = fromCurrency === DEFAULT_SENDER_CURRENCY
  // Whether to fire the preview at all only turns on the local checks
  // (format, zero, too large, native balance) — every daily/monthly outcome
  // (unknown, or over either) is equally previewable, so the rand value
  // isn't needed yet to decide this.
  const previewable = canPreview(amountIssue(debounced, limits))
  const preview = usePreview(debounced, fromCurrency, currency, previewable)
  const priced = settled && preview.isSuccess && !preview.isFetching
  const amountZar = isZar
    ? amount
    : priced
      ? preview.data.sender_amount_zar
      : undefined
  const debouncedZar = isZar
    ? debounced
    : priced
      ? preview.data.sender_amount_zar
      : undefined

  const issue =
    amountIssue(amount, limits, amountZar) ??
    (settled && isTooSmallForFees(preview.error) ? "too_small_for_fees" : null)
  const ratesUnavailable = settled && isRatesUnavailable(preview.error)
  // An empty field isn't a mistake yet; everything else is said at once.
  const showIssue = issue !== null && issue !== "empty"
  const name = beneficiaryName(beneficiary)
  const payoutOptions = beneficiary.payout_currencies
  const currencyItems = payoutOptions.map((value) => ({
    value,
    label: value,
  }))

  /** What `limitZar` is worth in `fromCurrency`, at the priced rate — only
   * once that rate is known, and only worth showing at all for another
   * currency (a ZAR figure needs no converting into itself). */
  function estimate(limitZar: string | undefined) {
    if (isZar || limitZar === undefined) return undefined
    if (!priced || debouncedZar === undefined || amountZar === undefined) {
      return undefined
    }
    return {
      amount: estimateInCurrency(limitZar, debounced, debouncedZar),
      currency: fromCurrency,
    }
  }

  const issueMessage =
    issue === null
      ? null
      : amountIssueMessage(
          issue,
          limits,
          fromCurrency,
          issue === "over_daily_limit"
            ? estimate(limits.dailyRemaining)
            : issue === "over_monthly_limit"
              ? estimate(limits.monthlyRemaining)
              : undefined
        )

  const fromItems = fromAccounts.map((account) => ({
    value: account.currency,
    label: account.currency,
  }))
  // One account (everyone's starting ZAR balance, before they've ever been
  // paid into another currency): nothing to choose, so no picker to show.
  const canChooseFrom = fromAccounts.length > 1

  return (
    <Card>
      <CardHeader>
        <CardTitle>How much are you sending?</CardTitle>
        <CardDescription>
          To {name}, from your {fromCurrency} balance.
        </CardDescription>
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
            {canChooseFrom ? (
              <Field>
                <FieldLabel htmlFor="send-from">Send from</FieldLabel>
                <Select
                  items={fromItems}
                  value={fromCurrency}
                  onValueChange={(next) => {
                    if (next) onFromChange(next)
                  }}
                >
                  <SelectTrigger id="send-from" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    <SelectGroup>
                      {fromItems.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <FieldDescription>
                  Sending limits are in rand, whichever balance this leaves
                  from.
                </FieldDescription>
              </Field>
            ) : null}
            <Field data-invalid={showIssue}>
              <FieldLabel htmlFor="send-amount">
                You send ({fromCurrency})
              </FieldLabel>
              <InputGroup>
                <InputGroupAddon>
                  <InputGroupText>
                    {currencySymbol(fromCurrency)}
                  </InputGroupText>
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
                  : `Available: ${formatMoney(limits.available, fromCurrency)}`}
                {limits.dailyRemaining === undefined
                  ? null
                  : ` · Left today: ${remainingLine(limits.dailyRemaining, estimate(limits.dailyRemaining))}`}
                {limits.monthlyRemaining === undefined
                  ? null
                  : ` · Left this month: ${remainingLine(limits.monthlyRemaining, estimate(limits.monthlyRemaining))}`}
              </FieldDescription>
              {showIssue && issueMessage ? (
                <FieldError>{issueMessage}</FieldError>
              ) : null}
            </Field>
            <Field>
              <FieldLabel htmlFor="send-currency">They receive in</FieldLabel>
              {currencyItems.length === 1 ? (
                <InputGroup>
                  <InputGroupInput
                    id="send-currency"
                    readOnly
                    value={currencyItems[0].label}
                  />
                </InputGroup>
              ) : (
                <Select
                  items={currencyItems}
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
                      {currencyItems.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              )}
              <FieldDescription>
                {payoutOptions.length === 1
                  ? `The only currency ${name} can receive in RemitX.`
                  : currency === beneficiary.payout_currency
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
                      {formatFiatToTokenExchangeRate(
                        preview.data.fiat_to_token_exchange_rate,
                        preview.data.sender_currency,
                        preview.data.token_name
                      )}
                    </DescriptionDetails>
                  </DescriptionItem>
                  <DescriptionItem>
                    <DescriptionTerm>Fees</DescriptionTerm>
                    <DescriptionDetails>
                      {formatMoney(
                        preview.data.sender_transaction_fee,
                        fromCurrency
                      )}
                    </DescriptionDetails>
                    <FieldDescription>
                      Plus{" "}
                      {formatMoney(
                        preview.data.exchange_rate_margin,
                        fromCurrency
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
