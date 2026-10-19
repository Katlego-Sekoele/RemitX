import { useQuery } from "@tanstack/react-query"
import { useMemo, useState } from "react"

import { sdk, type PayoutCurrency } from "~/client"
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
import { Skeleton } from "~/components/ui/skeleton"
import { useDebouncedValue } from "~/hooks/use-debounced-value"
import { errorMessage } from "~/hooks/use-onboarding"
import { currencySymbol, formatMoney } from "~/lib/money"
import {
  isPayoutCurrency,
  normalizeAmount,
  PREVIEW_DEBOUNCE_MS,
  sanitizeAmountInput,
} from "~/lib/send"
import {
  contributionIssue,
  contributionIssueMessage,
  LIVE_RATE_HINT,
  PREVIEW_MEMBER_CAP,
  type CreateSearch,
} from "~/lib/stokvel-create"
import { feeShare, poolAmount } from "~/lib/stokvels"

/**
 * What a full round's payout costs, priced like any transfer in the Stokvel
 * currency to a beneficiary paid in it. Each recipient's own payout currency
 * can add an exchange margin, so this is the lowest case. Nothing is held or
 * saved.
 */
function usePoolPreview(pool: string, currency: string, enabled: boolean) {
  const senderAmount = normalizeAmount(pool)
  const receiver: PayoutCurrency = isPayoutCurrency(currency) ? currency : "ZAR"
  return useQuery({
    queryKey: ["quotes", "preview", senderAmount, currency, receiver],
    queryFn: async ({ signal }) => {
      const { data } = await sdk.quotes.previewQuote({
        body: {
          sender_amount: senderAmount,
          sender_currency: currency,
          receiver_payout_currency: receiver,
        },
        signal,
        throwOnError: true,
      })
      return data
    },
    enabled,
    staleTime: 30_000,
  })
}

export function CreateAmountStep({
  search,
  currency,
  onChange,
  onBack,
  onContinue,
}: {
  search: CreateSearch
  /** The resolved Stokvel currency. */
  currency: string
  onChange: (patch: Partial<CreateSearch>) => void
  onBack: () => void
  onContinue: () => void
}) {
  const [touched, setTouched] = useState(false)
  const amountProblem = contributionIssue(search.amount)
  const valid = amountProblem === null

  // Members join by invitation after creation, so the preview assumes a
  // full stokvel: the largest a round's pool can be.
  const pool = useMemo(
    () =>
      amountProblem === null
        ? poolAmount(normalizeAmount(search.amount), PREVIEW_MEMBER_CAP)
        : null,
    [amountProblem, search.amount]
  )
  const debouncedPool = useDebouncedValue(pool, PREVIEW_DEBOUNCE_MS)
  const settled = debouncedPool === pool
  const preview = usePoolPreview(
    debouncedPool ?? "0",
    currency,
    debouncedPool !== null
  )
  const share = preview.data
    ? feeShare(
        preview.data.sender_transaction_fee,
        preview.data.exchange_rate_margin,
        PREVIEW_MEMBER_CAP
      )
    : undefined

  return (
    <Card>
      <form
        noValidate
        className="flex flex-col gap-(--card-spacing)"
        onSubmit={(event) => {
          event.preventDefault()
          setTouched(true)
          if (valid) onContinue()
        }}
      >
        <CardHeader>
          <CardTitle>Amount</CardTitle>
          <CardDescription>
            The same amount every round. {LIVE_RATE_HINT}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <FieldGroup>
            <Field data-invalid={touched && amountProblem !== null}>
              <FieldLabel htmlFor="stokvel-amount">
                Each member pays, per round
              </FieldLabel>
              <InputGroup>
                <InputGroupAddon>
                  <InputGroupText>{currencySymbol(currency)}</InputGroupText>
                </InputGroupAddon>
                <InputGroupInput
                  id="stokvel-amount"
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder="500.00"
                  value={search.amount}
                  aria-invalid={touched && amountProblem !== null}
                  onChange={(event) =>
                    onChange({
                      amount: sanitizeAmountInput(event.target.value),
                    })
                  }
                  onBlur={() => setTouched(true)}
                />
              </InputGroup>
              {touched && amountProblem ? (
                <FieldError>
                  {contributionIssueMessage(amountProblem, currency)}
                </FieldError>
              ) : (
                <FieldDescription>
                  Fixed for the whole stokvel. A different amount means a new
                  stokvel.
                </FieldDescription>
              )}
            </Field>
          </FieldGroup>

          {pool ? (
            <div className="flex flex-col gap-2 rounded-lg bg-muted p-4">
              <p className="text-sm font-medium">
                Each round, with {PREVIEW_MEMBER_CAP} members
              </p>
              <DescriptionList>
                <DescriptionItem>
                  <DescriptionTerm>Pool</DescriptionTerm>
                  <DescriptionDetails>
                    {formatMoney(pool, currency)}
                  </DescriptionDetails>
                </DescriptionItem>
                <DescriptionItem>
                  <DescriptionTerm>Fee per member, paid on top</DescriptionTerm>
                  <DescriptionDetails>
                    {!settled || preview.isPending ? (
                      <Skeleton className="h-4 w-20" />
                    ) : share ? (
                      `about ${formatMoney(share, currency)}`
                    ) : (
                      "—"
                    )}
                  </DescriptionDetails>
                </DescriptionItem>
                <DescriptionItem>
                  <DescriptionTerm>
                    Sent to the member&apos;s beneficiary
                  </DescriptionTerm>
                  <DescriptionDetails>
                    {formatMoney(pool, currency)}, the full pool
                  </DescriptionDetails>
                </DescriptionItem>
              </DescriptionList>
              <p className="text-xs text-muted-foreground">
                Each member&apos;s fee share is worked out when they pay. It is
                higher when that round&apos;s beneficiary is paid in another
                currency, because an exchange margin applies.
                {preview.error
                  ? ` Preview unavailable: ${errorMessage(preview.error)}`
                  : ""}
              </p>
            </div>
          ) : null}
        </CardContent>
        <CardFooter className="flex-wrap justify-between gap-2">
          <Button type="button" variant="outline" onClick={onBack}>
            Back
          </Button>
          <Button type="submit" disabled={touched && !valid}>
            Continue
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
