import { Skeleton } from "~/components/ui/skeleton"
import { useTokenRate } from "~/hooks/use-token-rate"
import { formatMoney } from "~/lib/money"
import { tokenToFiat } from "~/lib/stokvels"

/** "R500.00 at today's rate", from the fixed token amount (D13). The token is
 * never named on screen. */
export function ContributionAtTodaysRate({
  amount,
  currency,
}: {
  /** The stokvel's `contribution_amount`, in tokens. */
  amount: string
  currency: string
}) {
  const rate = useTokenRate(currency)
  if (rate.isPending) return <Skeleton className="inline-block h-3 w-24" />
  if (!rate.data) return <>Amount unavailable</>
  return (
    <>
      {formatMoney(tokenToFiat(amount, rate.data), currency)} at today&apos;s
      rate
    </>
  )
}
