"use client"

import { useReducedMotion } from "motion/react"
import { useEffect, useRef, type RefObject } from "react"

import { cn } from "~/lib/utils"

const LINE = "REMITX   SEND ZAR   STOKVEL   RLUSD   "

export type AsciiPointer = {
  x: number
  y: number
  tx: number
  ty: number
}

export function createAsciiPointer(): AsciiPointer {
  return { x: -2000, y: -2000, tx: -2000, ty: -2000 }
}

type Rgb = { r: number; g: number; b: number }

function parseRgb(value: string): Rgb {
  const match = value.match(/[\d.]+/g)
  if (!match || match.length < 3) return { r: 20, g: 24, b: 32 }
  return {
    r: Number(match[0]),
    g: Number(match[1]),
    b: Number(match[2]),
  }
}

function rgba({ r, g, b }: Rgb, alpha: number) {
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * A tiled word field. Characters near the pointer brighten and step aside,
 * in the spirit of a text-matrix hover.
 */
export function AsciiTextField({
  className,
  pointerRef,
}: {
  className?: string
  pointerRef: RefObject<AsciiPointer>
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const foregroundRef = useRef<HTMLSpanElement>(null)
  const primaryRef = useRef<HTMLSpanElement>(null)
  const reduce = useReducedMotion()

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    const foregroundProbe = foregroundRef.current
    const primaryProbe = primaryRef.current
    if (!canvas || !wrap || !foregroundProbe || !primaryProbe) return

    const context = canvas.getContext("2d")
    if (!context) return

    let frame = 0
    let width = 0
    let height = 0
    let visible = true
    const colors = {
      foreground: parseRgb("rgb(20, 24, 32)"),
      primary: parseRgb("rgb(215, 33, 105)"),
    }

    const readColors = () => {
      colors.foreground = parseRgb(getComputedStyle(foregroundProbe).color)
      colors.primary = parseRgb(getComputedStyle(primaryProbe).color)
    }

    const resize = () => {
      const bounds = wrap.getBoundingClientRect()
      width = bounds.width
      height = bounds.height
      const dpr = Math.min(window.devicePixelRatio || 1, 1.75)
      canvas.width = Math.max(1, Math.floor(width * dpr))
      canvas.height = Math.max(1, Math.floor(height * dpr))
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      readColors()
    }

    const draw = (time: number) => {
      if (width < 1 || height < 1) return
      const pointer = pointerRef.current
      if (reduce) {
        pointer.x = pointer.tx
        pointer.y = pointer.ty
      } else {
        pointer.x += (pointer.tx - pointer.x) * 0.16
        pointer.y += (pointer.ty - pointer.y) * 0.16
      }

      context.clearRect(0, 0, width, height)
      const fontSize = width < 640 ? 10 : 12
      context.font = `500 ${fontSize}px "JetBrains Mono Variable", ui-monospace, monospace`
      context.textBaseline = "top"
      const cellWidth = context.measureText("M").width
      const cellHeight = fontSize * 1.55
      const columns = Math.ceil(width / cellWidth) + 1
      const rows = Math.ceil(height / cellHeight) + 1
      const radius = Math.min(width, height) * 0.28

      for (let row = 0; row < rows; row += 1) {
        for (let column = 0; column < columns; column += 1) {
          const character = LINE[column % LINE.length] ?? " "
          if (character === " ") continue

          let x = column * cellWidth
          let y = row * cellHeight
          const dx = x - pointer.x
          const dy = y - pointer.y
          const distance = Math.hypot(dx, dy)
          const hover = Math.exp(-(distance * distance) / (2 * radius * radius))
          const wave = reduce
            ? 0
            : Math.max(0, Math.sin(column * 0.45 - time * 0.0014 + row * 0.2))
          const glow = Math.max(hover, wave * 0.28)

          if (!reduce && hover > 0.02) {
            const push = hover * 12
            const length = distance || 1
            x += (dx / length) * push
            y += (dy / length) * push
          }

          context.fillStyle = rgba(colors.foreground, 0.08 + glow * 0.2)
          context.fillText(character, x, y)
          if (glow > 0.18) {
            context.fillStyle = rgba(colors.primary, (glow - 0.18) * 0.95)
            context.fillText(character, x, y)
          }
        }
      }
    }

    resize()
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(wrap)
    const themeObserver = new MutationObserver(readColors)
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    })
    const visibility = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? true
    })
    visibility.observe(wrap)

    const tick = (time: number) => {
      frame = window.requestAnimationFrame(tick)
      if (!visible) return
      draw(time)
    }
    frame = window.requestAnimationFrame(tick)

    return () => {
      window.cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      themeObserver.disconnect()
      visibility.disconnect()
    }
  }, [pointerRef, reduce])

  return (
    <div
      ref={wrapRef}
      aria-hidden
      className={cn("pointer-events-none overflow-hidden", className)}
    >
      <span
        ref={foregroundRef}
        className="absolute size-px text-foreground opacity-0"
      />
      <span
        ref={primaryRef}
        className="absolute size-px text-primary opacity-0"
      />
      <canvas ref={canvasRef} className="block h-full w-full" />
    </div>
  )
}
