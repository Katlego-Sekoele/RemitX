import { useId } from "react"

import { cn } from "~/lib/utils"

export type CardFeature = {
  title: string
  description: string
}

export function FeaturesSectionCards({
  features,
  className,
}: {
  features: CardFeature[]
  className?: string
}) {
  return (
    <div
      className={cn(
        "mx-auto grid max-w-7xl grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 md:gap-3 lg:grid-cols-4",
        className
      )}
    >
      {features.map((feature) => (
        <div
          key={feature.title}
          className="relative overflow-hidden rounded-3xl border border-border bg-card p-6"
        >
          <Grid size={20} />
          <p className="relative z-20 font-heading text-base font-semibold text-foreground">
            {feature.title}
          </p>
          <p className="relative z-20 mt-4 text-base text-muted-foreground">
            {feature.description}
          </p>
        </div>
      ))}
    </div>
  )
}

function Grid({ pattern, size = 20 }: { pattern?: number[][]; size?: number }) {
  const patternSquares = pattern ?? [
    [8, 2],
    [9, 4],
    [7, 3],
    [10, 1],
    [8, 5],
  ]
  return (
    <div className="pointer-events-none absolute inset-0 opacity-40">
      <GridPattern
        width={size}
        height={size}
        offsetX="-12"
        offsetY="4"
        squares={patternSquares}
        className="absolute inset-0 h-full w-full fill-foreground/5 stroke-foreground/10"
      />
    </div>
  )
}

function GridPattern({
  width,
  height,
  offsetX,
  offsetY,
  squares,
  ...props
}: {
  width: number
  height: number
  offsetX: string
  offsetY: string
  squares?: number[][]
  className?: string
}) {
  const patternId = useId()

  return (
    <svg aria-hidden="true" {...props}>
      <defs>
        <pattern
          id={patternId}
          width={width}
          height={height}
          patternUnits="userSpaceOnUse"
          x={offsetX}
          y={offsetY}
        >
          <path d={`M.5 ${height}V.5H${width}`} fill="none" />
        </pattern>
      </defs>
      <rect
        width="100%"
        height="100%"
        strokeWidth={0}
        fill={`url(#${patternId})`}
      />
      {squares ? (
        <svg x={offsetX} y={offsetY} className="overflow-visible">
          {squares.map(([gridColumn, gridRow]) => (
            <rect
              strokeWidth="0"
              key={`${gridColumn}-${gridRow}`}
              width={width + 1}
              height={height + 1}
              x={gridColumn * width}
              y={gridRow * height}
            />
          ))}
        </svg>
      ) : null}
    </svg>
  )
}
