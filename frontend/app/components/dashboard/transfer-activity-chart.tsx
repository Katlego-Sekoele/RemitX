import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"

import type { ActivityDayRead } from "~/client"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "~/components/ui/chart"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  chartAmount,
  formatChartDay,
  formatChartMoney,
} from "~/lib/chart-series"

const chartConfig = {
  zarSent: { label: "ZAR sent", color: "var(--chart-1)" },
  payoutReceived: {
    label: "Payout received",
    color: "var(--chart-2)",
  },
} satisfies ChartConfig

function formatPayoutReceived(value: unknown): string {
  const numeric = typeof value === "number" ? value : Number(value)
  if (!Number.isFinite(numeric)) return ""
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric)
}

/** ZAR sent and payout-currency received over the last 30 UTC days. */
export function TransferActivityChart({
  activity,
}: {
  activity: ActivityDayRead[]
}) {
  const data = activity.map((day) => ({
    day: day.day,
    zarSent: chartAmount(day.zar_sent),
    payoutReceived: chartAmount(day.payout_received),
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity</CardTitle>
        <CardDescription>
          ZAR you sent and what you received in payout currency, by day. Failed
          transfers are left out.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={chartConfig}
          className="aspect-auto h-64 w-full"
        >
          <AreaChart data={data}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="day"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={24}
              tickFormatter={formatChartDay}
            />
            <YAxis yAxisId="zar" tickLine={false} axisLine={false} width={40} />
            <YAxis
              yAxisId="payout"
              orientation="right"
              tickLine={false}
              axisLine={false}
              width={40}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={(value) => formatChartDay(String(value))}
                  formatter={(value, name) =>
                    name === "payoutReceived"
                      ? formatPayoutReceived(value)
                      : formatChartMoney(value, "ZAR")
                  }
                />
              }
            />
            <Area
              yAxisId="zar"
              dataKey="zarSent"
              type="monotone"
              fill="var(--color-zarSent)"
              fillOpacity={0.25}
              stroke="var(--color-zarSent)"
            />
            <Area
              yAxisId="payout"
              dataKey="payoutReceived"
              type="monotone"
              fill="var(--color-payoutReceived)"
              fillOpacity={0.25}
              stroke="var(--color-payoutReceived)"
            />
            <ChartLegend content={<ChartLegendContent />} />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
