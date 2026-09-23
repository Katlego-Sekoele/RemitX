import { ClockIcon, WarningCircleIcon } from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef } from "react"
import { useNavigate } from "react-router"
import { toast } from "sonner"

import { api, sdk, type BeneficiaryRead as Beneficiary } from "~/client"
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { FieldDescription } from "~/components/ui/field"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "~/components/ui/item"
import { Skeleton } from "~/components/ui/skeleton"
import { Table, TableBody, TableCell, TableRow } from "~/components/ui/table"
import { useNow } from "~/hooks/use-now"
import { errorMessage } from "~/hooks/use-onboarding"
import { beneficiaryName } from "~/lib/beneficiaries"
import { SETTLEMENT_TOKEN_LABEL, SETTLEMENT_TOKEN_NOTE } from "~/lib/money"
import {
  confirmRefusal,
  formatCountdown,
  quoteLines,
  quoteRefusal,
  RATES_UNAVAILABLE_MESSAGE,
  secondsLeft,
  SENDER_CURRENCY,
  type PayoutCurrency,
} from "~/lib/send"

/**
 * Creating a quote holds a price, so it's a POST, but it's read like a
 * query: one per visit to Review, shared by a remount (React's strict mode
 * mounts twice), dropped as soon as the sender leaves the step (`gcTime: 0`)
 * so coming back prices afresh, and refetched on demand for a new quote.
 */
function useQuote(
  beneficiaryId: string,
  amount: string,
  currency: PayoutCurrency
) {
  return useQuery({
    queryKey: ["quotes", "create", beneficiaryId, amount, currency],
    queryFn: async () => {
      const { data } = await sdk.quotes.createQuote({
        body: {
          beneficiary_id: beneficiaryId,
          sender_amount: amount,
          sender_currency: SENDER_CURRENCY,
          receiver_payout_currency: currency,
        },
        throwOnError: true,
      })
      return data
    },
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 0,
    retry: false,
  })
}

export function ReviewStep({
  beneficiary,
  amount,
  currency,
  onBack,
}: {
  beneficiary: Beneficiary
  amount: string
  currency: PayoutCurrency
  onBack: () => void
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const now = useNow()
  const quote = useQuote(beneficiary.beneficiary_id, amount, currency)

  // Set synchronously on the first click: a double click lands both clicks
  // before React re-renders the button disabled.
  const confirming = useRef(false)
  const confirm = useMutation({
    ...api.remittances.confirmRemittance(),
    onSettled: (_data, error) => {
      if (error) confirming.current = false
    },
    onSuccess: (remittance) => {
      queryClient.invalidateQueries({
        queryKey: api.accounts.getAccounts().queryKey,
      })
      toast.success("Transfer sent")
      navigate(`/app/transfers/${remittance.remittance_id}`)
    },
    onError: (error) => {
      const refusal = confirmRefusal(error)
      if (refusal === "unverified") {
        queryClient.invalidateQueries({
          queryKey: api.kyc.onboarding.getApplication().queryKey,
        })
        return
      }
      // Known refusals render their own alert. Anything else is announced
      // here as well as inline, so a 500 or a network failure is not silent.
      if (refusal === "other") toast.error(errorMessage(error))
    },
  })

  // Not verified any more: the page's gate shows the verification card.
  const quoteUnverified =
    quote.isError && quoteRefusal(quote.error) === "unverified"
  useEffect(() => {
    if (quoteUnverified) {
      queryClient.invalidateQueries({
        queryKey: api.kyc.onboarding.getApplication().queryKey,
      })
    }
  }, [quoteUnverified, queryClient])

  const newQuote = () => {
    confirm.reset()
    quote.refetch()
  }

  if (quote.isPending || (quote.isFetching && !confirm.isPending)) {
    return <Skeleton className="h-96 w-full" />
  }

  if (quote.isError) {
    const refusal = quoteRefusal(quote.error)
    return (
      <div className="flex flex-col gap-4">
        <Alert variant="destructive">
          <WarningCircleIcon />
          <AlertTitle>
            {refusal === "rates_unavailable"
              ? RATES_UNAVAILABLE_MESSAGE
              : "We couldn't price this transfer"}
          </AlertTitle>
          <AlertDescription>
            {refusal === "rates_unavailable"
              ? "Try again in a few minutes."
              : errorMessage(quote.error)}
          </AlertDescription>
        </Alert>
        <div className="flex justify-between gap-2">
          <Button variant="outline" onClick={onBack}>
            Back
          </Button>
          {refusal === "rates_unavailable" ? (
            <Button onClick={() => quote.refetch()}>Try again</Button>
          ) : null}
        </div>
      </div>
    )
  }

  const data = quote.data
  const seconds = secondsLeft(data.expires_at, now)
  const refusal = confirm.isError ? confirmRefusal(confirm.error) : null
  // A quote can't be confirmed once its price has lapsed or the API has
  // said it's used or expired; only a new quote moves on from there.
  const stale = seconds === 0 || refusal === "quote_inactive"
  const sending = confirm.isPending || confirm.isSuccess

  return (
    <div className="flex flex-col gap-6">
      <Item variant="outline">
        <ItemContent>
          <ItemTitle>{beneficiaryName(beneficiary)}</ItemTitle>
          <ItemDescription>
            Receives {data.receiver_currency} · Paid from your ZAR balance
          </ItemDescription>
        </ItemContent>
        <ItemActions>
          <Badge variant={stale ? "destructive" : "secondary"}>
            <ClockIcon aria-hidden="true" />
            <span role="timer" aria-live="off">
              {stale
                ? "Price expired"
                : `Price held for ${formatCountdown(seconds)}`}
            </span>
          </Badge>
        </ItemActions>
      </Item>

      <Table>
        <TableBody>
          {quoteLines(data).map((line, index, lines) => (
            <TableRow key={line.label}>
              <TableCell>
                {index === lines.length - 1 ? (
                  <ItemTitle>{line.label}</ItemTitle>
                ) : (
                  line.label
                )}
              </TableCell>
              <TableCell>
                <div className="flex flex-col items-end gap-0.5">
                  {index === lines.length - 1 ? (
                    <ItemTitle>{line.value}</ItemTitle>
                  ) : (
                    line.value
                  )}
                  {line.detail ? (
                    <FieldDescription>{line.detail}</FieldDescription>
                  ) : null}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <FieldDescription>
        {SETTLEMENT_TOKEN_LABEL}: {SETTLEMENT_TOKEN_NOTE}
      </FieldDescription>

      {stale ? (
        <Alert variant="destructive">
          <WarningCircleIcon />
          <AlertTitle>
            {refusal === "quote_inactive"
              ? "This quote has been used or has expired"
              : "This price has expired"}
          </AlertTitle>
          <AlertDescription>
            Rates move, so prices are only held for a short while. Get a new
            quote to carry on.
          </AlertDescription>
          <AlertAction>
            <Button size="sm" onClick={newQuote}>
              Get a new quote
            </Button>
          </AlertAction>
        </Alert>
      ) : refusal === "insufficient_balance" ? (
        <Alert variant="destructive">
          <WarningCircleIcon />
          <AlertTitle>Your balance no longer covers this transfer</AlertTitle>
          <AlertDescription>
            Another transfer may have spent it first. Add money to your ZAR
            balance by EFT, then get a new quote.
          </AlertDescription>
          <AlertAction>
            <Button size="sm" variant="outline" onClick={newQuote}>
              Get a new quote
            </Button>
          </AlertAction>
        </Alert>
      ) : refusal === "other" ? (
        <Alert variant="destructive">
          <WarningCircleIcon />
          <AlertTitle>We couldn&apos;t send this transfer</AlertTitle>
          <AlertDescription>{errorMessage(confirm.error)}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex justify-between gap-2">
        <Button variant="outline" disabled={sending} onClick={onBack}>
          Back
        </Button>
        <Button
          disabled={stale || sending || refusal === "insufficient_balance"}
          onClick={() => {
            if (confirming.current) return
            confirming.current = true
            confirm.mutate({ body: { quote_id: data.quote_id } })
          }}
        >
          {sending ? "Sending…" : "Confirm and send"}
        </Button>
      </div>
    </div>
  )
}
