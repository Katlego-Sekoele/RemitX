/**
 * Declarative rules for which site chrome to show on each route.
 *
 * First matching rule wins. Add a row here when a new route group needs its
 * own chrome — avoid branching inside ``AppChrome`` itself.
 */
export type ChromeMode = "hidden" | "auth" | "marketing" | "compact"

type ChromeRule = {
  id: string
  mode: ChromeMode
  match: (pathname: string) => boolean
}

export const CHROME_RULES: readonly ChromeRule[] = [
  {
    id: "admin",
    mode: "hidden",
    match: (pathname) =>
      pathname === "/admin" || pathname.startsWith("/admin/"),
  },
  {
    id: "app",
    mode: "hidden",
    match: (pathname) => pathname === "/app" || pathname.startsWith("/app/"),
  },
  {
    id: "onboarding-legacy",
    mode: "hidden",
    match: (pathname) =>
      pathname === "/onboarding" || pathname.startsWith("/onboarding/"),
  },
  {
    id: "auth",
    mode: "auth",
    match: (pathname) =>
      pathname.startsWith("/sign-in") || pathname.startsWith("/sign-up"),
  },
  {
    id: "marketing",
    mode: "marketing",
    match: (pathname) => pathname === "/",
  },
] as const

export const DEFAULT_CHROME_MODE: ChromeMode = "compact"

export function resolveChromeMode(pathname: string): ChromeMode {
  for (const rule of CHROME_RULES) {
    if (rule.match(pathname)) return rule.mode
  }
  return DEFAULT_CHROME_MODE
}
