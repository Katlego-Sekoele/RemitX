/**
 * Resolve a CSS color (including `var(--token)` / oklch / color-mix) to an
 * `rgb()` / `rgba()` string. Three.js does not understand oklch; modern
 * browsers often return oklch from getComputedStyle instead of rgb.
 */
export function resolveCssColor(expression: string): string {
  if (typeof document === "undefined") return "rgb(0, 0, 0)"

  const probe = document.createElement("div")
  probe.style.color = expression
  document.documentElement.appendChild(probe)
  const computed = getComputedStyle(probe).color
  probe.remove()

  return toThreeColor(computed)
}

/** Force any browser-resolved CSS color into rgb/rgba for Three.js. */
export function toThreeColor(cssColor: string): string {
  if (typeof document === "undefined") return "rgb(0, 0, 0)"
  if (!cssColor || cssColor === "transparent") return "rgba(0, 0, 0, 0)"

  const canvas = document.createElement("canvas")
  canvas.width = 1
  canvas.height = 1
  const context = canvas.getContext("2d", { willReadFrequently: true })
  if (!context) return "rgb(0, 0, 0)"

  context.clearRect(0, 0, 1, 1)
  context.fillStyle = cssColor
  context.fillRect(0, 0, 1, 1)
  const [redChannel, greenChannel, blueChannel, alphaByte] =
    context.getImageData(0, 0, 1, 1).data

  if (alphaByte < 255) {
    return `rgba(${redChannel}, ${greenChannel}, ${blueChannel}, ${Number((alphaByte / 255).toFixed(3))})`
  }
  return `rgb(${redChannel}, ${greenChannel}, ${blueChannel})`
}

export function themeColor(token: `--${string}`): string {
  return resolveCssColor(`var(${token})`)
}

/** Theme color with alpha (0–1), via color-mix so tokens stay authoritative. */
export function themeColorAlpha(token: `--${string}`, alpha: number): string {
  const percent = Math.round(alpha * 100)
  return resolveCssColor(
    `color-mix(in oklch, var(${token}) ${percent}%, transparent)`
  )
}
