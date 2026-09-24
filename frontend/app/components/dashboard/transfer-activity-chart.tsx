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
import { SETTLEMENT_TOKEN_LABEL, TOKEN_CURRENCY } from "~/lib/money"

const chartConfig = {
  zarSent: { label: "ZAR sent", color: "var(--chart-1)" },
  tokenReceived: {
    label: `${SETTLEMENT_TOKEN_LABEL} received`,
    color: "var(--chart-2)",
  },
} satisfies ChartConfig

/** ZAR sent and RLUSD received over the last 30 UTC days. */
export function TransferActivityChart({
  activity,
}: {
  activity: ActivityDayRead[]
}) {
  const data = activity.map((day) => ({
    day: day.day,
    zarSent: chartAmount(day.zar_sent),
    tokenReceived: chartAmount(day.token_received),
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity</CardTitle>
        <CardDescription>
          ZAR you sent and {SETTLEMENT_TOKEN_LABEL} you received, by day. Failed
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
              yAxisId="token"
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
                    formatChartMoney(
                      value,
                      name === "tokenReceived" ? TOKEN_CURRENCY : "ZAR"
                    )
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
              yAxisId="token"
              dataKey="tokenReceived"
              type="monotone"
              fill="var(--color-tokenReceived)"
              fillOpacity={0.25}
              stroke="var(--color-tokenReceived)"
            />
            <ChartLegend content={<ChartLegendContent />} />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
