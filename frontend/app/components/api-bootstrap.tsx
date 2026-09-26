import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"

import { api } from "~/client"
import { setSettlementTokenCurrency } from "~/lib/money"

/**
 * Loads public API metadata once so money helpers know the settlement token's
 * ledger currency code (Config.UCTUSD_TOKEN_NAME), without duplicating it in
 * the frontend env.
 */
export function ApiBootstrap() {
  const { data } = useQuery({
    ...api.system.health(),
    staleTime: Number.POSITIVE_INFINITY,
  })

  useEffect(() => {
    if (data?.settlement_token_currency) {
      setSettlementTokenCurrency(data.settlement_token_currency)
    }
  }, [data?.settlement_token_currency])

  return null
}
