"use client"

import type {
  HTMLAttributes,
  MouseEvent as ReactMouseEvent,
  ReactNode,
} from "react"
import { motion, useMotionTemplate, useMotionValue } from "motion/react"

import { cn } from "~/lib/utils"

type SpotlightCardProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
  radius?: number
}

export function SpotlightCard({
  children,
  className,
  radius = 320,
  ...props
}: SpotlightCardProps) {
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)

  const spotlight = useMotionTemplate`radial-gradient(${radius}px circle at ${mouseX}px ${mouseY}px, var(--accent), transparent 80%)`

  function handleMouseMove({
    currentTarget,
    clientX,
    clientY,
  }: ReactMouseEvent<HTMLDivElement>) {
    const { left, top } = currentTarget.getBoundingClientRect()
    mouseX.set(clientX - left)
    mouseY.set(clientY - top)
  }

  return (
    <div
      className={cn("group/spotlight relative", className)}
      onMouseMove={handleMouseMove}
      {...props}
    >
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -inset-px opacity-0 transition-opacity duration-500 group-hover/spotlight:opacity-100"
        style={{ background: spotlight }}
      />
      <div className="relative w-full">{children}</div>
    </div>
  )
}
