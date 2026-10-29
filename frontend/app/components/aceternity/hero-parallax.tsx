"use client"

import {
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "motion/react"
import { useRef, type ReactNode } from "react"

import { cn } from "~/lib/utils"

export type ParallaxCard = {
  title: string
  content: ReactNode
}

const SPRING = { stiffness: 140, damping: 28, mass: 0.35 }

/**
 * Scroll-linked 3D card rows. Motion model adapted from Aceternity UI's
 * hero parallax: the rows counter-translate as the section rotates flat.
 */
export function HeroParallax({
  cards,
  header,
  className,
}: {
  cards: ParallaxCard[]
  header: ReactNode
  className?: string
}) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLElement>(null)
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  })
  const translateX = useSpring(
    useTransform(scrollYProgress, [0, 1], [0, 520]),
    SPRING
  )
  const translateXReverse = useSpring(
    useTransform(scrollYProgress, [0, 1], [0, -520]),
    SPRING
  )
  const rotateX = useSpring(
    useTransform(scrollYProgress, [0, 0.28], [16, 0]),
    SPRING
  )
  const rotateZ = useSpring(
    useTransform(scrollYProgress, [0, 0.28], [10, 0]),
    SPRING
  )
  const translateY = useSpring(
    useTransform(scrollYProgress, [0, 0.28], [-420, 180]),
    SPRING
  )
  const opacity = useSpring(
    useTransform(scrollYProgress, [0, 0.2], [0.45, 1]),
    SPRING
  )

  const rows = [
    { items: cards.slice(0, 5), translate: translateX, reverse: true },
    { items: cards.slice(5, 10), translate: translateXReverse, reverse: false },
    { items: cards.slice(10, 15), translate: translateX, reverse: true },
  ]

  if (reduce) {
    return (
      <section
        id="product"
        className={cn(
          "scroll-mt-24 border-b border-border px-6 py-20 lg:py-28",
          className
        )}
      >
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-10">
          {header}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {cards.slice(0, 6).map((card) => (
              <div key={card.title} className="h-80">
                {card.content}
              </div>
            ))}
          </div>
        </div>
      </section>
    )
  }

  return (
    <section
      ref={ref}
      id="product"
      className={cn(
        "relative h-[200vh] scroll-mt-24 overflow-hidden border-b border-border [perspective:1200px]",
        className
      )}
    >
      <div className="relative z-20 bg-background">
        <div className="mx-auto w-full max-w-6xl px-6 pt-16 pb-6">{header}</div>
      </div>
      <div className="pointer-events-none relative z-20 h-16 bg-gradient-to-b from-background to-transparent" />
      <motion.div
        style={{ rotateX, rotateZ, translateY, opacity }}
        className="[transform-style:preserve-3d]"
      >
        {rows.map((row) =>
          row.items.length === 0 ? null : (
            <ParallaxRow key={row.items[0]?.title} row={row} />
          )
        )}
      </motion.div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 h-28 bg-gradient-to-t from-background to-transparent" />
    </section>
  )
}

function ParallaxRow({
  row,
}: {
  row: {
    items: ParallaxCard[]
    translate: MotionValue<number>
    reverse: boolean
  }
}) {
  return (
    <motion.div
      className={cn(
        "mb-8 flex gap-6 px-[6vw] md:mb-12 md:gap-10",
        row.reverse && "flex-row-reverse"
      )}
    >
      {row.items.map((card) => (
        <motion.div
          key={card.title}
          style={{ x: row.translate }}
          whileHover={{ y: -16 }}
          className="h-80 w-72 shrink-0 md:w-[26rem]"
        >
          {card.content}
        </motion.div>
      ))}
    </motion.div>
  )
}
