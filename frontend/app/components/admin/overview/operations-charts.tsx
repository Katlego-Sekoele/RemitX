import { useState } from "react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts"
import { useQuery } from "@tanstack/react-query"

import { api } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "~/components/ui/chart"
import { Skeleton } from "~/components/ui/skeleton"
import { useHasPermission } from "~/hooks/use-permissions"
import {
  chartAmount,
  formatChartDay,
  formatChartMoney,
  lastDays,
} from "~/lib/chart-series"
import { SETTLEMENT_TOKEN_LABEL } from "~/lib/money"
import { PERMISSIONS } from "~/lib/permissions"

const volumeConfig = {
  zarCashIn: { label: "ZAR cash-in", color: "var(--chart-1)" },
  tokenSettled: {
    label: `${SETTLEMENT_TOKEN_LABEL} settled`,
    color: "var(--chart-2)",
  },
} satisfies ChartConfig

const pipelineConfig = {
  queued: { label: "Queued", color: "var(--chart-4)" },
  settling: { label: "Settling", color: "var(--chart-2)" },
  settled: { label: "Settled", color: "var(--chart-1)" },
  failed: { label: "Failed", color: "var(--chart-5)" },
} satisfies ChartConfig

type Window = 7 | 30

/** Confirmed volume and the settlement pipeline, for staff who can read transfers. */
export function OperationsCharts() {
  const canRead = useHasPermission(PERMISSIONS.transactionReadAny)
  const [days, setDays] = useState<Window>(30)
  const operations = useQuery({
    ...api.admin.operations.getOperations(),
    enabled: canRead,
  })

  if (!canRead) return null
  if (operations.isPending) return <Skeleton className="h-64" />
  if (operations.isError) {
    return (
      <QueryError
        title="Couldn't load settlement activity"
        error={operations.error}
        onRetry={() => operations.refetch()}
      />
    )
  }

  const volume = lastDays(operations.data.volume, days).map((day) => ({
    day: day.day,
    zarCashIn: chartAmount(day.zar_cash_in),
    tokenSettled: chartAmount(day.token_settled),
  }))
  const pipeline = lastDays(operations.data.pipeline, days)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          size="sm"
          variant={days === 7 ? "default" : "outline"}
          onClick={() => setDays(7)}
        >
          7 days
        </Button>
        <Button
          size="sm"
          variant={days === 30 ? "default" : "outline"}
          onClick={() => setDays(30)}
        >
          30 days
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Volume</CardTitle>
          <CardDescription>
            Confirmed ZAR cash-in and {SETTLEMENT_TOKEN_LABEL} settled, by day.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer
            config={volumeConfig}
            className="aspect-auto h-64 w-full"
          >
            <AreaChart data={volume}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="day"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={24}
                tickFormatter={formatChartDay}
              />
              <YAxis
                yAxisId="zar"
                tickLine={false}
                axisLine={false}
                width={40}
              />
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
                      name === "tokenSettled"
                        ? formatChartMoney(value, "", "settlement")
                        : formatChartMoney(value, "ZAR")
                    }
                  />
                }
              />
              <Area
                yAxisId="zar"
                dataKey="zarCashIn"
                type="monotone"
                fill="var(--color-zarCashIn)"
                fillOpacity={0.25}
                stroke="var(--color-zarCashIn)"
              />
              <Area
                yAxisId="token"
                dataKey="tokenSettled"
                type="monotone"
                fill="var(--color-tokenSettled)"
                fillOpacity={0.25}
                stroke="var(--color-tokenSettled)"
              />
              <ChartLegend content={<ChartLegendContent />} />
            </AreaChart>
          </ChartContainer>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Pipeline</CardTitle>
          <CardDescription>
            Transfers started each day, by where settlement stands now.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer
            config={pipelineConfig}
            className="aspect-auto h-64 w-full"
          >
            <BarChart data={pipeline}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="day"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={24}
                tickFormatter={formatChartDay}
              />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) => formatChartDay(String(value))}
                  />
                }
              />
              <Bar
                dataKey="queued"
                stackId="status"
                fill="var(--color-queued)"
              />
              <Bar
                dataKey="settling"
                stackId="status"
                fill="var(--color-settling)"
              />
              <Bar
                dataKey="settled"
                stackId="status"
                fill="var(--color-settled)"
              />
              <Bar
                dataKey="failed"
                stackId="status"
                fill="var(--color-failed)"
              />
              <ChartLegend content={<ChartLegendContent />} />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </div>
  )
}
