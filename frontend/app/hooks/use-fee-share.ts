import { useQuery } from "@tanstack/react-query"

import { sdk, type PayoutCurrency } from "~/client"
import { isPayoutCurrency } from "~/lib/send"
import { feeShare, poolAmount } from "~/lib/stokvels"

/**
 * An estimate of each member's fee share for a round, paid on top of the
 * contribution (D6, #340): the quote preview's fee and margin on the whole
 * pool into the recipient's payout currency, split evenly and rounded up, as
 * the API's `contribution_fee_share` does. The API fixes the real share when
 * the member pays, at that moment's rate, and returns it as `fee_amount`.
 *
 * `payoutCurrency` is the round recipient's when known; otherwise the Stokvel
 * currency, which has no margin, so the estimate is the lowest it can be.
 */
export function useFeeShareEstimate({
  contribution,
  currency,
  memberCount,
  payoutCurrency,
  enabled = true,
}: {
  /** One member's contribution in the Stokvel currency. */
  contribution: string
  currency: string
  memberCount: number
  payoutCurrency: string | null
  enabled?: boolean
}) {
  const pool = poolAmount(contribution, memberCount)
  const receiver: PayoutCurrency =
    payoutCurrency && isPayoutCurrency(payoutCurrency)
      ? payoutCurrency
      : isPayoutCurrency(currency)
        ? currency
        : "ZAR"
  return useQuery({
    queryKey: ["quotes", "preview", "fee-share", pool, currency, receiver],
    queryFn: async ({ signal }) => {
      const { data } = await sdk.quotes.previewQuote({
        body: {
          sender_amount: pool,
          sender_currency: currency,
          receiver_payout_currency: receiver,
        },
        signal,
        throwOnError: true,
      })
      return feeShare(
        data.sender_transaction_fee,
        data.exchange_rate_margin,
        memberCount
      )
    },
    enabled: enabled && memberCount > 0,
    staleTime: 30_000,
  })
}
