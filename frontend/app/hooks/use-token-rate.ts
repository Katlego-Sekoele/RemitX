import { useQuery } from "@tanstack/react-query"

import { sdk, type PayoutCurrency } from "~/client"
import { isPayoutCurrency } from "~/lib/send"

/** Large enough to cover the transfer fee, which the preview refuses below. */
const PROBE_AMOUNT = "1000.00"

/**
 * The live token units per 1 `currency`, from the quote preview (the same
 * rate the send flow prices with). Stokvel amounts are fixed in tokens (D13),
 * so the screens use this to show them in the Stokvel currency and the create
 * wizard to fix the token amount. The receiver side does not change this
 * rate, so it is the Stokvel currency itself. Nothing is held or saved.
 */
export function useTokenRate(currency: string) {
  const receiver: PayoutCurrency = isPayoutCurrency(currency) ? currency : "ZAR"
  return useQuery({
    queryKey: ["quotes", "preview", "token-rate", currency],
    queryFn: async ({ signal }) => {
      const { data } = await sdk.quotes.previewQuote({
        body: {
          sender_amount: PROBE_AMOUNT,
          sender_currency: currency,
          receiver_payout_currency: receiver,
        },
        signal,
        throwOnError: true,
      })
      return data.fiat_to_token_exchange_rate
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}
