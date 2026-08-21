import type { ReactNode } from "react"

import { cn } from "~/lib/utils"

export type HoverFeature = {
  title: string
  description: string
  icon: ReactNode
}

export function FeaturesSectionHover({
  features,
  className,
}: {
  features: HoverFeature[]
  className?: string
}) {
  return (
    <div
      className={cn(
        "relative z-10 mx-auto grid max-w-7xl grid-cols-1 md:grid-cols-2 lg:grid-cols-4",
        className
      )}
    >
      {features.map((feature, index) => (
        <Feature key={feature.title} {...feature} index={index} />
      ))}
    </div>
  )
}

function Feature({
  title,
  description,
  icon,
  index,
}: HoverFeature & { index: number }) {
  return (
    <div
      className={cn(
        "group/feature relative flex flex-col border-border py-10 lg:border-r",
        (index === 0 || index === 4) && "lg:border-l",
        index < 4 && "lg:border-b"
      )}
    >
      <div className="pointer-events-none absolute inset-0 h-full w-full bg-muted opacity-0 transition duration-200 group-hover/feature:opacity-100" />
      <div className="relative z-10 mb-4 px-10 text-muted-foreground">
        {icon}
      </div>
      <div className="relative z-10 mb-2 px-10 text-lg font-semibold">
        <div className="absolute inset-y-0 left-0 h-6 w-1 origin-center rounded-r-full bg-muted-foreground/40 transition-all duration-200 group-hover/feature:h-8 group-hover/feature:bg-primary" />
        <span className="inline-block text-foreground transition duration-200 group-hover/feature:translate-x-2">
          {title}
        </span>
      </div>
      <p className="relative z-10 max-w-xs px-10 text-sm text-muted-foreground">
        {description}
      </p>
    </div>
  )
}
