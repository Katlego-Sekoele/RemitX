import type { LimitHeadroomRead } from "~/client"
import { ShareRadial } from "~/components/dashboard/share-radial"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { usedShare } from "~/lib/chart-series"
import { formatMoney, isZeroMoney } from "~/lib/money"

/** Daily and monthly ZAR already sent, against the caller's allowance. */
export function LimitHeadroom({ limits }: { limits: LimitHeadroomRead }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sending limits</CardTitle>
        <CardDescription>
          ZAR sent today and this month, including transfers still settling.
          Failed transfers are not counted.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 sm:grid-cols-2">
        <Allowance
          title="Today"
          sent={limits.daily_sent_zar}
          limit={limits.daily_limit_zar}
        />
        <Allowance
          title="This month"
          sent={limits.monthly_sent_zar}
          limit={limits.monthly_limit_zar}
        />
      </CardContent>
    </Card>
  )
}

function Allowance({
  title,
  sent,
  limit,
}: {
  title: string
  sent: string
  limit: string
}) {
  const share = usedShare(sent, limit)
  const caption = isZeroMoney(limit)
    ? "No allowance yet"
    : `${formatMoney(sent, "ZAR")} of ${formatMoney(limit, "ZAR")}`

  return (
    <div className="flex flex-col items-center gap-2">
      <ShareRadial share={share} label={`${Math.round(share * 100)}%`} />
      <p className="font-medium">{title}</p>
      <p className="text-muted-foreground">{caption}</p>
    </div>
  )
}
