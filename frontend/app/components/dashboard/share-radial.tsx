import {
  Label,
  PolarGrid,
  PolarRadiusAxis,
  RadialBar,
  RadialBarChart,
} from "recharts"

import { ChartContainer, type ChartConfig } from "~/components/ui/chart"

const chartConfig = {
  share: { label: "Used", color: "var(--chart-1)" },
} satisfies ChartConfig

/** A ring whose arc is `share` of a full turn (0–1). `label` sits in the hole. */
export function ShareRadial({
  share,
  label,
}: {
  share: number
  label: string
}) {
  const turn = Math.min(1, Math.max(0, share))

  return (
    <ChartContainer
      config={chartConfig}
      className="mx-auto aspect-square h-36"
      initialDimension={{ width: 144, height: 144 }}
    >
      <RadialBarChart
        data={[{ share: 100, fill: "var(--color-share)" }]}
        startAngle={90}
        endAngle={90 - turn * 360}
        innerRadius={48}
        outerRadius={68}
      >
        <PolarGrid
          gridType="circle"
          radialLines={false}
          stroke="none"
          polarRadius={[54, 42]}
        />
        <RadialBar dataKey="share" background cornerRadius={6} />
        <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
          <Label
            content={({ viewBox }) => {
              if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                return (
                  <text
                    x={viewBox.cx}
                    y={viewBox.cy}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="fill-foreground text-sm font-medium"
                  >
                    {label}
                  </text>
                )
              }
            }}
          />
        </PolarRadiusAxis>
      </RadialBarChart>
    </ChartContainer>
  )
}
