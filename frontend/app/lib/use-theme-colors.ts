import { useSyncExternalStore } from "react"

import { resolveCssColor, themeColor, themeColorAlpha } from "~/lib/css-color"

export type ThemeColors = {
  primary: string
  background: string
  foreground: string
  /** Near-white fill for lights (illuminates the sphere). */
  light: string
  /** Ocean / sphere base — contrast-tuned per scheme. */
  globe: string
  /** Continent hex fill. */
  land: string
}

export type ThemeColorState = ThemeColors & { scheme: "light" | "dark" }

const FALLBACK_LIGHT: ThemeColorState = {
  primary: "rgb(215, 33, 105)",
  background: "rgb(248, 250, 252)",
  foreground: "rgb(34, 45, 58)",
  light: "rgb(255, 255, 255)",
  globe: "rgb(200, 213, 226)",
  land: "rgba(34, 45, 58, 0.4)",
  scheme: "light",
}

function readThemeColors(dark: boolean): ThemeColors {
  return {
    primary: themeColor("--primary"),
    background: themeColor("--background"),
    foreground: themeColor("--foreground"),
    // WebGL lights need a bright color. Do NOT use --primary-foreground in dark
    // mode — that token is near-black for readable text on the light primary.
    light: dark
      ? themeColor("--foreground")
      : themeColor("--primary-foreground"),
    globe: dark
      ? resolveCssColor(
          "color-mix(in oklch, var(--card) 70%, var(--foreground) 30%)"
        )
      : resolveCssColor(
          "color-mix(in oklch, var(--muted) 75%, var(--foreground) 25%)"
        ),
    land: themeColorAlpha("--foreground", dark ? 0.6 : 0.4),
  }
}

function isDarkScheme(): boolean {
  return document.documentElement.classList.contains("dark")
}

let cached: ThemeColorState | null = null

function getSnapshot(): ThemeColorState {
  const dark = isDarkScheme()
  const scheme = dark ? "dark" : "light"
  if (cached?.scheme === scheme) return cached
  cached = { ...readThemeColors(dark), scheme }
  return cached
}

function getServerSnapshot(): ThemeColorState {
  return FALLBACK_LIGHT
}

function subscribe(onStoreChange: () => void): () => void {
  const notify = () => {
    cached = null
    onStoreChange()
  }

  const observer = new MutationObserver(notify)
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  })

  const media = window.matchMedia("(prefers-color-scheme: dark)")
  media.addEventListener("change", notify)

  return () => {
    observer.disconnect()
    media.removeEventListener("change", notify)
  }
}

/**
 * Theme tokens for WebGL, synced to the `dark` class on <html>.
 * Reads CSS vars in the snapshot so colors match the scheme on the same
 * render as a theme toggle (no useEffect lag).
 */
export function useThemeColors(): ThemeColorState {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
