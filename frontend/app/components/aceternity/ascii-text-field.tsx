"use client"

import { useReducedMotion } from "motion/react"
import { useEffect, useRef, type RefObject } from "react"

import { cn } from "~/lib/utils"

const LINE = "REMITX·SEND·STOKVEL·RLUSD·"
const LOGO_SRC = "/remitx-logo.svg"

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

type SafeRect = {
  left: number
  top: number
  right: number
  bottom: number
  pad: number
}

function gamma(channel: number) {
  const clamped = Math.min(1, Math.max(0, channel))
  const encoded =
    clamped <= 0.0031308
      ? 12.92 * clamped
      : 1.055 * clamped ** (1 / 2.4) - 0.055
  return Math.round(encoded * 255)
}

/** `getComputedStyle` returns oklch here, and the canvas fill rejects it. */
function oklchToRgb(lightness: number, chroma: number, hue: number): Rgb {
  const a = chroma * Math.cos((hue * Math.PI) / 180)
  const b = chroma * Math.sin((hue * Math.PI) / 180)
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3
  return {
    r: gamma(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    g: gamma(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    b: gamma(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  }
}

function parseRgb(value: string): Rgb {
  const oklch = value.match(/oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)/)
  if (oklch) {
    return oklchToRgb(Number(oklch[1]), Number(oklch[2]), Number(oklch[3]))
  }
  const rgb = value.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/)
  if (rgb) {
    return { r: Number(rgb[1]), g: Number(rgb[2]), b: Number(rgb[3]) }
  }
  return { r: 236, g: 238, b: 242 }
}

function rgba({ r, g, b }: Rgb, alpha: number) {
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/** 0 inside a padded safe rect, rising to 1 across a short feather. */
function clearance(x: number, y: number, rects: SafeRect[]) {
  let keep = 1
  for (const rect of rects) {
    const left = rect.left - rect.pad
    const top = rect.top - rect.pad
    const right = rect.right + rect.pad
    const bottom = rect.bottom + rect.pad
    const dx = Math.max(left - x, 0, x - right)
    const dy = Math.max(top - y, 0, y - bottom)
    const distance = Math.hypot(dx, dy)
    const feather = 36
    if (distance < feather) keep = Math.min(keep, distance / feather)
  }
  return keep
}

/**
 * The RemitX mark, drawn as words. Characters exist only on the logo
 * silhouette. Regions marked `data-ascii-safe` stay clear, with padding.
 */
export function AsciiTextField({
  className,
  pointerRef,
  boundsRef,
}: {
  className?: string
  pointerRef: RefObject<AsciiPointer>
  boundsRef: RefObject<HTMLElement | null>
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
    let columns = 0
    let rows = 0
    let cellWidth = 8
    let cellHeight = 14
    let mask: Float32Array | null = null
    let visible = true
    const colors = {
      foreground: parseRgb("rgb(20, 24, 32)"),
      primary: parseRgb("rgb(215, 33, 105)"),
    }

    const readColors = () => {
      colors.foreground = parseRgb(getComputedStyle(foregroundProbe).color)
      colors.primary = parseRgb(getComputedStyle(primaryProbe).color)
    }

    const image = new Image()
    image.src = LOGO_SRC

    const buildMask = () => {
      if (!image.complete || image.naturalWidth === 0 || width < 1) return
      const fontSize = width < 640 ? 10 : 11
      context.font = `500 ${fontSize}px "JetBrains Mono Variable", ui-monospace, monospace`
      cellWidth = context.measureText("M").width
      cellHeight = fontSize * 1.35
      columns = Math.max(1, Math.ceil(width / cellWidth))
      rows = Math.max(1, Math.ceil(height / cellHeight))

      const sample = document.createElement("canvas")
      sample.width = columns
      sample.height = rows
      const sampleContext = sample.getContext("2d", {
        willReadFrequently: true,
      })
      if (!sampleContext) return

      const wide = width >= 960
      const mark = Math.min(height * 0.96, width * (wide ? 0.7 : 0.92))
      const originX = (wide ? width * 0.7 : width * 0.5) - mark / 2
      const originY = height * 0.5 - mark / 2
      sampleContext.drawImage(
        image,
        originX / cellWidth,
        originY / cellHeight,
        mark / cellWidth,
        mark / cellHeight
      )
      const pixels = sampleContext.getImageData(0, 0, columns, rows).data
      const next = new Float32Array(columns * rows)
      for (let index = 0; index < next.length; index += 1) {
        next[index] = (pixels[index * 4 + 3] ?? 0) / 255
      }
      mask = next
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
      buildMask()
    }

    const safeRects = (): SafeRect[] => {
      const root = boundsRef.current
      if (!root) return []
      const origin = wrap.getBoundingClientRect()
      return [...root.querySelectorAll<HTMLElement>("[data-ascii-safe]")].map(
        (node) => {
          const rect = node.getBoundingClientRect()
          const pad = Number(node.dataset.asciiPad ?? "40")
          return {
            left: rect.left - origin.left,
            top: rect.top - origin.top,
            right: rect.right - origin.left,
            bottom: rect.bottom - origin.top,
            pad: Number.isFinite(pad) ? pad : 40,
          }
        }
      )
    }

    const draw = () => {
      if (!mask || width < 1 || height < 1 || columns < 1) return
      const pointer = pointerRef.current
      if (reduce) {
        pointer.x = pointer.tx
        pointer.y = pointer.ty
      } else {
        pointer.x += (pointer.tx - pointer.x) * 0.16
        pointer.y += (pointer.ty - pointer.y) * 0.16
      }

      context.clearRect(0, 0, width, height)
      const fontSize = width < 640 ? 10 : 11
      context.font = `500 ${fontSize}px "JetBrains Mono Variable", ui-monospace, monospace`
      context.textBaseline = "middle"
      const rects = safeRects()
      const radius = 150

      for (let row = 0; row < rows; row += 1) {
        for (let column = 0; column < columns; column += 1) {
          const coverage = mask[row * columns + column] ?? 0
          if (coverage < 0.45) continue

          let x = column * cellWidth + cellWidth / 2
          let y = row * cellHeight + cellHeight / 2
          const open = clearance(x, y, rects)
          if (open <= 0) continue

          const dx = x - pointer.x
          const dy = y - pointer.y
          const distance = Math.hypot(dx, dy)
          const hover = Math.exp(-(distance * distance) / (2 * radius * radius))

          if (!reduce && hover > 0.04) {
            const push = hover * 7
            const length = distance || 1
            x += (dx / length) * push
            y += (dy / length) * push
          }

          const seen = open
          const character = LINE[column % LINE.length] ?? "·"
          context.fillStyle = rgba(colors.foreground, seen)
          context.fillText(character, x, y)
          if (hover > 0.08) {
            context.fillStyle = rgba(colors.primary, seen * hover * 0.9)
            context.fillText(character, x, y)
          }
        }
      }
    }

    image.onload = () => buildMask()
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

    const tick = () => {
      frame = window.requestAnimationFrame(tick)
      if (!visible) return
      draw()
    }
    frame = window.requestAnimationFrame(tick)

    return () => {
      window.cancelAnimationFrame(frame)
      image.onload = null
      resizeObserver.disconnect()
      themeObserver.disconnect()
      visibility.disconnect()
    }
  }, [boundsRef, pointerRef, reduce])

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
