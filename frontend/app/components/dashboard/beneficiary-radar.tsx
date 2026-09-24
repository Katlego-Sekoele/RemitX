import { PolarAngleAxis, PolarGrid, Radar, RadarChart } from "recharts"

import type { BeneficiarySpendRead } from "~/client"
import {
  ChartContainer,
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
import { chartAmount, formatChartMoney } from "~/lib/chart-series"

const chartConfig = {
  zarSent: { label: "ZAR sent", color: "var(--chart-1)" },
} satisfies ChartConfig

/** Who the caller has paid the most, by ZAR sent. */
export function BeneficiaryRadar({ rows }: { rows: BeneficiarySpendRead[] }) {
  const data = rows.map((row) => ({
    name: row.name,
    zarSent: chartAmount(row.zar_sent),
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Who you pay</CardTitle>
        <CardDescription>
          The people you have sent the most ZAR to. Failed transfers are left
          out.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={chartConfig}
          className="mx-auto aspect-square h-72 w-full"
        >
          <RadarChart data={data}>
            <PolarGrid />
            <PolarAngleAxis dataKey="name" />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  formatter={(value) => formatChartMoney(value, "ZAR")}
                />
              }
            />
            <Radar
              dataKey="zarSent"
              fill="var(--color-zarSent)"
              fillOpacity={0.4}
              stroke="var(--color-zarSent)"
            />
          </RadarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
