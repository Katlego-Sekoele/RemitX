import type { ReactNode } from "react"

import { cn } from "~/lib/utils"

type GridBackgroundProps = {
  children: ReactNode
  className?: string
}

export function GridBackground({ children, className }: GridBackgroundProps) {
  return (
    <div className={cn("relative flex min-h-svh w-full flex-col", className)}>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_70%)] bg-[size:4rem_4rem]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,var(--accent)_0%,transparent_45%)] opacity-[0.07]"
      />
      <div className="relative z-10 flex flex-1 flex-col">{children}</div>
    </div>
  )
}
