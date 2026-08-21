# Landing Page and Auth UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the RemitX placeholder home with a marketing landing and upgrade Clerk sign-in/sign-up to a split layout that shares an Aceternity globe with the landing hero.

**Architecture:** Install Aceternity’s GitHub Globe, wrap it in a RemitX-themed lazy `GlobeDemo`, compose a theme-aware `AuthSplitLayout` around Clerk, and rebuild `/` as hero + how-it-works + trust + footer. Chrome gains landing CTAs and hides the redundant Sign-in button on auth routes.

**Tech Stack:** React Router v7 SPA, Clerk (`@clerk/react-router`), shadcn/ui, Aceternity `@aceternity/globe`, Three.js / R3F / three-globe (registry deps), Motion (existing), next-themes, Phosphor icons, Tailwind v4.

**Spec:** [docs/superpowers/specs/2026-08-21-landing-and-auth-ui-design.md](../specs/2026-08-21-landing-and-auth-ui-design.md)

## Global Constraints

- **No git commits** unless the user later asks. Skip every Commit step.
- **UI standard:** compose from shadcn/ui and Aceternity. Tailwind for layout only.
- **Icons:** `@phosphor-icons/react` only (not Lucide).
- **Prettier:** no semicolons, double quotes, 2-space indent, 80 cols.
- **Path alias:** `~/*` → `app/*`. Aceternity files live in `frontend/app/components/aceternity/`.
- **Clerk stays:** do not replace `SignIn` / `SignUp` with custom forms. Keep splat routes.
- **Theme-aware:** no forced dark-only panels; use CSS tokens. Globe Three materials use hex samples that match light/dark RemitX colors.
- **XRPL Testnet / academic prototype copy** on landing and auth; no real-funds implication.
- **Do not edit** `.env` or commit secrets.

## File map

| Path | Responsibility |
|---|---|
| `frontend/app/components/aceternity/globe.tsx` | Aceternity `World` / `Globe` (CLI install, relocated) |
| `frontend/app/data/globe.json` | Country polygons for the globe |
| `frontend/app/components/aceternity/globe-demo.tsx` | RemitX arcs + theme-aware config; default export |
| `frontend/app/components/aceternity/lazy-globe-demo.tsx` | `React.lazy` + Suspense wrapper used by landing/auth |
| `frontend/app/components/auth-split-layout.tsx` | Split visual \| children layout |
| `frontend/app/components/landing/landing-hero.tsx` | First viewport |
| `frontend/app/components/landing/how-it-works.tsx` | Four journey beats |
| `frontend/app/components/landing/trust-note.tsx` | Trust section |
| `frontend/app/components/landing/landing-footer.tsx` | Footer |
| `frontend/app/routes/home.tsx` | Compose landing sections |
| `frontend/app/routes/sign-in.tsx` | AuthSplitLayout + Clerk SignIn |
| `frontend/app/routes/sign-up.tsx` | AuthSplitLayout + Clerk SignUp |
| `frontend/app/components/app-chrome.tsx` | Landing bar CTAs; hide Sign-in on auth routes |
| `frontend/app/lib/site.ts` | SEO/title copy update |
| `frontend/app/components/ui/separator.tsx` | shadcn separator (if missing after add) |
| `frontend/package.json` / lockfile | Globe transitive deps |

---

### Task 1: Install Aceternity globe + data

**Files:**
- Create: `frontend/app/components/aceternity/globe.tsx`
- Create: `frontend/app/data/globe.json`
- Modify: `frontend/package.json`, `frontend/package-lock.json`
- Possibly create then delete: `frontend/components/ui/globe.tsx` (CLI default path)

**Interfaces:**
- Consumes: Aceternity registry `@aceternity/globe`
- Produces: `export function World(props: { globeConfig: GlobeConfig; data: Position[] }): JSX.Element` and related types from `~/components/aceternity/globe`

- [ ] **Step 1: Install the registry component**

```bash
cd frontend
npx shadcn@latest add @aceternity/globe --yes
```

Expected: dependencies `three`, `three-globe`, `@react-three/fiber`, `@react-three/drei` added; a `globe.tsx` file written (often under `components/ui/` or `app/components/ui/`).

- [ ] **Step 2: Relocate into aceternity and fix imports**

Move the file to `frontend/app/components/aceternity/globe.tsx`.

Change the countries import to:

```ts
import countries from "~/data/globe.json"
```

Change any `@/lib/utils` import to `~/lib/utils` if present.

Ensure `tsconfig` / Vite can resolve JSON modules (React Router frontend already allows JSON imports if used elsewhere; if `tsc` errors on JSON, add `"resolveJsonModule": true` under `compilerOptions` in `frontend/tsconfig.json`).

- [ ] **Step 3: Download globe data**

```bash
mkdir -p frontend/app/data
curl -fsSL https://ui.aceternity.com/globe.json -o frontend/app/data/globe.json
```

Expected: non-empty JSON file (countries FeatureCollection / polygon payload).

- [ ] **Step 4: Remove stray CLI paths**

Delete leftover `frontend/components/ui/globe.tsx` or `frontend/app/components/ui/globe.tsx` if the CLI wrote there and you already copied to aceternity. Do not leave duplicate `Globe`/`World` exports.

- [ ] **Step 5: Typecheck that the module resolves**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -40
```

Expected: no errors specifically about missing `~/components/aceternity/globe` or `~/data/globe.json`. Other pre-existing errors (if any) are out of scope; new globe-related errors must be fixed.

- [ ] **Step 6: Commit** — **SKIP** (user requested no commits)

---

### Task 2: RemitX `GlobeDemo` + lazy wrapper

**Files:**
- Create: `frontend/app/components/aceternity/globe-demo.tsx`
- Create: `frontend/app/components/aceternity/lazy-globe-demo.tsx`

**Interfaces:**
- Consumes: `World` from `~/components/aceternity/globe`; `useTheme` from `next-themes`
- Produces:
  - `export default function GlobeDemo(): JSX.Element`
  - `export function LazyGlobeDemo(props: { className?: string }): JSX.Element`

- [ ] **Step 1: Implement `globe-demo.tsx`**

Use Cape Town–anchored arcs and theme-aware hex configs. Deterministic colors (no `Math.random`).

```tsx
import { useTheme } from "next-themes"
import { World } from "~/components/aceternity/globe"

type Arc = {
  order: number
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  arcAlt: number
  color: string
}

const CPT = { lat: -33.9249, lng: 18.4241 }

const DESTINATIONS = [
  { lat: 51.5072, lng: -0.1276 }, // London
  { lat: 40.7128, lng: -74.006 }, // New York
  { lat: -1.2921, lng: 36.8219 }, // Nairobi
  { lat: 25.2048, lng: 55.2708 }, // Dubai
  { lat: -26.2041, lng: 28.0473 }, // Johannesburg
]

export default function GlobeDemo() {
  const { resolvedTheme } = useTheme()
  const dark = resolvedTheme === "dark"

  const colors = dark
    ? ["#F43F5E", "#3B82C4", "#7DD3FC"]
    : ["#E11D48", "#2563A8", "#01213B"]

  const globeConfig = dark
    ? {
        pointSize: 4,
        globeColor: "#01213B",
        showAtmosphere: true,
        atmosphereColor: "#FFFFFF",
        atmosphereAltitude: 0.1,
        emissive: "#01213B",
        emissiveIntensity: 0.15,
        shininess: 0.9,
        polygonColor: "rgba(255,255,255,0.55)",
        ambientLight: "#7DD3FC",
        directionalLeftLight: "#ffffff",
        directionalTopLight: "#ffffff",
        pointLight: "#ffffff",
        arcTime: 1000,
        arcLength: 0.9,
        rings: 1,
        maxRings: 3,
        initialPosition: CPT,
        autoRotate: true,
        autoRotateSpeed: 0.45,
      }
    : {
        pointSize: 4,
        globeColor: "#0B3A5C",
        showAtmosphere: true,
        atmosphereColor: "#E8F1F8",
        atmosphereAltitude: 0.12,
        emissive: "#0B3A5C",
        emissiveIntensity: 0.08,
        shininess: 0.85,
        polygonColor: "rgba(255,255,255,0.45)",
        ambientLight: "#93C5FD",
        directionalLeftLight: "#ffffff",
        directionalTopLight: "#ffffff",
        pointLight: "#ffffff",
        arcTime: 1000,
        arcLength: 0.9,
        rings: 1,
        maxRings: 3,
        initialPosition: CPT,
        autoRotate: true,
        autoRotateSpeed: 0.45,
      }

  const sampleArcs: Arc[] = DESTINATIONS.map((end, i) => ({
    order: i + 1,
    startLat: CPT.lat,
    startLng: CPT.lng,
    endLat: end.lat,
    endLng: end.lng,
    arcAlt: 0.15 + (i % 3) * 0.12,
    color: colors[i % colors.length]!,
  }))

  return (
    <div className="absolute inset-0 size-full">
      <World globeConfig={globeConfig} data={sampleArcs} />
    </div>
  )
}
```

If `World`’s Canvas requires an explicit height parent, wrap with `className="h-full w-full"` on an inner div matching Aceternity demo sizing (`h-[20rem]` / `aspect` as needed for auth vs hero — prefer parent-driven `absolute inset-0`).

- [ ] **Step 2: Implement lazy wrapper**

```tsx
import { lazy, Suspense } from "react"

import { cn } from "~/lib/utils"

const GlobeDemo = lazy(() => import("~/components/aceternity/globe-demo"))

type LazyGlobeDemoProps = {
  className?: string
}

export function LazyGlobeDemo({ className }: LazyGlobeDemoProps) {
  return (
    <div className={cn("relative size-full overflow-hidden", className)}>
      <Suspense
        fallback={<div className="size-full bg-muted" aria-hidden="true" />}
      >
        <GlobeDemo />
      </Suspense>
    </div>
  )
}
```

- [ ] **Step 3: Sanity import check**

```bash
cd frontend && npm run typecheck
```

Expected: PASS (or only unrelated pre-existing failures). Fix any `World` prop / JSON typing issues in this task.

- [ ] **Step 4: Commit** — **SKIP**

---

### Task 3: `AuthSplitLayout` + wire sign-in / sign-up

**Files:**
- Create: `frontend/app/components/auth-split-layout.tsx`
- Modify: `frontend/app/routes/sign-in.tsx`
- Modify: `frontend/app/routes/sign-up.tsx`
- Create (if missing): `frontend/app/components/ui/separator.tsx` via shadcn

**Interfaces:**
- Consumes: `LazyGlobeDemo`; Clerk children; `SITE_NAME` / tagline from `~/lib/site`
- Produces: `export function AuthSplitLayout(props: { children: ReactNode }): JSX.Element`

- [ ] **Step 1: Add separator if not present**

```bash
cd frontend && test -f app/components/ui/separator.tsx || npx shadcn@latest add separator --yes
```

- [ ] **Step 2: Implement `auth-split-layout.tsx`**

```tsx
import type { ReactNode } from "react"
import { Link } from "react-router"

import { LazyGlobeDemo } from "~/components/aceternity/lazy-globe-demo"
import { SITE_NAME, SITE_TAGLINE } from "~/lib/site"

type AuthSplitLayoutProps = {
  children: ReactNode
}

export function AuthSplitLayout({ children }: AuthSplitLayoutProps) {
  return (
    <div className="flex min-h-svh w-full">
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-border bg-muted/40 lg:flex">
        <Link
          to="/"
          className="relative z-20 flex items-center gap-2.5 p-8"
          aria-label={`${SITE_NAME} home`}
        >
          <img src="/remitx-logo.svg" alt="" className="size-8" />
          <span className="text-sm font-semibold text-foreground">
            {SITE_NAME}
          </span>
        </Link>

        <div className="absolute inset-0 flex items-center justify-center">
          <LazyGlobeDemo className="h-full max-h-[36rem] w-full max-w-[36rem]" />
        </div>

        <div className="relative z-20 mt-auto p-8">
          <p className="text-sm text-muted-foreground">
            ZAR → RLUSD on XRPL Testnet. Academic prototype — no real funds.
          </p>
        </div>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center bg-background px-6 py-12">
        <div className="mb-8 flex flex-col items-center gap-2 lg:hidden">
          <Link to="/" aria-label={`${SITE_NAME} home`}>
            <img src="/remitx-logo.svg" alt="" className="size-10" />
          </Link>
          <p className="text-center text-sm text-muted-foreground">
            {SITE_TAGLINE}
          </p>
        </div>
        <div className="flex w-full max-w-sm flex-col items-center gap-4">
          {children}
          <p className="text-center text-xs text-muted-foreground">
            XRPL Testnet only. No real remittances or customer funds.
          </p>
        </div>
      </div>
    </div>
  )
}
```

Do not hard-code dark zinc panels. Use `bg-background`, `bg-muted/40`, `border-border`, `text-muted-foreground`.

- [ ] **Step 3: Replace sign-in page**

`frontend/app/routes/sign-in.tsx`:

```tsx
import { SignIn } from "@clerk/react-router"

import { AuthSplitLayout } from "~/components/auth-split-layout"
import type { Route } from "./+types/sign-in"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Sign in — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function SignInPage() {
  return (
    <AuthSplitLayout>
      <SignIn signUpUrl="/sign-up" />
    </AuthSplitLayout>
  )
}
```

- [ ] **Step 4: Replace sign-up page**

Mirror sign-in with `SignUp` and `signInUrl="/sign-in"`, title `Sign up — RemitX`.

- [ ] **Step 5: Manual check**

Run: `cd frontend && npm run dev`  
Open `/sign-in` and `/sign-up` at ≥1024px and under 1024px, light and dark.

Expected: split + globe on large screens; compact brand + Clerk on small; theme toggle still works (chrome task may still show Sign-in button until Task 5).

- [ ] **Step 6: Commit** — **SKIP**

---

### Task 4: Landing page sections + home route + site copy

**Files:**
- Create: `frontend/app/components/landing/landing-hero.tsx`
- Create: `frontend/app/components/landing/how-it-works.tsx`
- Create: `frontend/app/components/landing/trust-note.tsx`
- Create: `frontend/app/components/landing/landing-footer.tsx`
- Modify: `frontend/app/routes/home.tsx`
- Modify: `frontend/app/lib/site.ts`

**Interfaces:**
- Consumes: `LazyGlobeDemo`, `FadeIn`, shadcn `Button`/`Badge`/`Card`/`Separator`, Phosphor icons, `Link`
- Produces: section components with no props (or optional `className` only)

- [ ] **Step 1: Update `site.ts`**

```ts
export const SITE_NAME = "RemitX"

export const SITE_TAGLINE = "Cross-border FX remittance"

export const SITE_TITLE = `${SITE_NAME} — ZAR to RLUSD`

export const SITE_DESCRIPTION =
  "Send South African rand and settle in RLUSD on the XRP Ledger Testnet. Academic prototype for UCT ECO5040W — no real funds."

export const SITE_SOCIAL_DESCRIPTION =
  "Cross-border remittance from South African rand to RLUSD on the XRP Ledger Testnet."

// keep SITE_URL, SOCIAL_IMAGE_*, THEME_COLOR unchanged
```

- [ ] **Step 2: Implement `landing-hero.tsx`**

Requirements from spec:

- Full-bleed globe behind/around content (not an inset card)
- **RemitX** as hero brand signal (logo + wordmark larger than headline)
- One headline, one supporting sentence, CTA group (Get started → `/sign-up`, Sign in → `/sign-in`)
- Theme tokens only; use `Button` variants
- `FadeIn` for text block
- Min height `min-h-svh`; content readable in light and dark

Sketch:

```tsx
import { Link } from "react-router"
import { SignInButton } from "@clerk/react-router"

import { FadeIn } from "~/components/aceternity/fade-in"
import { LazyGlobeDemo } from "~/components/aceternity/lazy-globe-demo"
import { Button } from "~/components/ui/button"
import { SITE_NAME } from "~/lib/site"

export function LandingHero() {
  return (
    <section className="relative flex min-h-svh w-full flex-col justify-end overflow-hidden">
      <div className="pointer-events-none absolute inset-0 opacity-80">
        <LazyGlobeDemo />
      </div>
      <div className="relative z-10 mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 pb-20 pt-32">
        <FadeIn>
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <img src="/remitx-logo.svg" alt="" className="size-14" />
              <span className="text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
                {SITE_NAME}
              </span>
            </div>
            <h1 className="max-w-xl text-xl text-foreground md:text-2xl">
              Send ZAR. Settle RLUSD on the XRP Ledger.
            </h1>
            <p className="max-w-lg text-sm text-muted-foreground md:text-base">
              A cross-border FX remittance prototype for UCT ECO5040W —
              XRPL Testnet only, no real funds.
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Button size="lg" render={<Link to="/sign-up" />}>
                Get started
              </Button>
              <SignInButton>
                <Button size="lg" variant="outline">
                  Sign in
                </Button>
              </SignInButton>
            </div>
          </div>
        </FadeIn>
      </div>
    </section>
  )
}
```

Adjust Base UI `render` prop usage to match existing `HomeLink` / Button patterns in the repo if the sketch’s `render={<Link />}` differs from current Button API.

- [ ] **Step 3: Implement `how-it-works.tsx`**

Four beats with Phosphor icons (`IdentificationCard`, `CurrencyCircleDollar`, `Queue`, `Wallet` or equivalent):

1. Register & mock KYC
2. Quote fees (ZAR → RLUSD)
3. Confirm ZAR cash-in → async XRPL settlement
4. Recipient wallet / simulated cash-out

Use a simple vertical/responsive grid. Prefer non-card layout with `Separator` between beats if cards feel decorative; use shadcn `Card` only if it aids scanning. One section title + one supporting sentence + four labeled steps.

- [ ] **Step 4: Implement `trust-note.tsx`**

Short section: custodial wallet, encrypted XRPL private keys, queued settlement. One headline, one short paragraph, optional three muted labels — no legal essay.

- [ ] **Step 5: Implement `landing-footer.tsx`**

```tsx
import { SITE_NAME } from "~/lib/site"

export function LandingFooter() {
  return (
    <footer className="border-t border-border px-6 py-10">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 text-sm text-muted-foreground">
        <p>{SITE_NAME} · UCT ECO5040W Financial Software Engineering</p>
        <p>
          Academic prototype on XRPL Testnet. No real customer funds or
          production remittances.
        </p>
      </div>
    </footer>
  )
}
```

- [ ] **Step 6: Compose `home.tsx`**

```tsx
import { HowItWorks } from "~/components/landing/how-it-works"
import { LandingFooter } from "~/components/landing/landing-footer"
import { LandingHero } from "~/components/landing/landing-hero"
import { TrustNote } from "~/components/landing/trust-note"

export default function Home() {
  return (
    <div className="flex w-full flex-col">
      <LandingHero />
      <HowItWorks />
      <TrustNote />
      <LandingFooter />
    </div>
  )
}
```

Remove the old under-construction `GridBackground` / 3d-card placeholder.

- [ ] **Step 7: Lint**

```bash
cd frontend && npm run lint
```

Expected: PASS. Fix Prettier/type issues.

- [ ] **Step 8: Commit** — **SKIP**

---

### Task 5: App chrome for landing vs auth

**Files:**
- Modify: `frontend/app/components/app-chrome.tsx`

**Interfaces:**
- Consumes: `useLocation` from `react-router`; existing Clerk `Show` / `SignInButton` / `UserButton`
- Produces: updated `AppChrome` behaviour (same export name)

- [ ] **Step 1: Update chrome behaviour**

Rules:

1. If path starts with `/sign-in` or `/sign-up`: hide `HomeLink` and the Sign-in button. Keep `ThemeToggle` in `ChromeBar`.
2. Else: show `HomeLink` + auth controls + theme toggle. When signed out, include Get started → `/sign-up` next to Sign-in.

```tsx
import { useLocation, Link } from "react-router"
import { Show, SignInButton, UserButton } from "@clerk/react-router"

import { ThemeToggle } from "~/components/theme-toggle"
import { Button } from "~/components/ui/button"

export function AppChrome() {
  const { pathname } = useLocation()
  const onAuth =
    pathname.startsWith("/sign-in") || pathname.startsWith("/sign-up")

  if (onAuth) {
    return (
      <ChromeBar>
        <ThemeToggle />
      </ChromeBar>
    )
  }

  return (
    <>
      <HomeLink />
      <ChromeBar>
        <Show
          when="signed-in"
          fallback={
            <>
              <Button
                size="sm"
                variant="outline"
                render={<Link to="/sign-up" />}
              >
                Get started
              </Button>
              <SignInButton>
                <Button size="sm">Sign in</Button>
              </SignInButton>
            </>
          }
        >
          <UserButton />
        </Show>
        <ThemeToggle />
      </ChromeBar>
    </>
  )
}
```

Keep exported `ChromeBar` / `HomeLink` for the error boundary.

- [ ] **Step 2: Visual verify**

- `/` — home link, Get started, Sign in, theme toggle
- `/sign-in`, `/sign-up` — theme toggle only in chrome; no duplicate Sign-in
- Signed-in: `UserButton` on landing

- [ ] **Step 3: Commit** — **SKIP**

---

### Task 6: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Typecheck + format check**

```bash
cd frontend && npm run lint
```

Expected: exit 0.

- [ ] **Step 2: Dev server smoke**

```bash
cd frontend && npm run dev
```

Checklist:

- [ ] Landing hero shows RemitX brand, one headline, CTAs, globe (light + dark)
- [ ] How it works has exactly four beats
- [ ] Trust + footer show academic/testnet disclaimer
- [ ] `/sign-in` and `/sign-up` split layout on desktop; stacked on mobile
- [ ] Clerk multi-step still works (navigate a sign-up flow far enough to hit a subpath)
- [ ] Theme toggle works on all three routes
- [ ] No console errors that block interaction (WebGL warnings alone are OK)

- [ ] **Step 3: Commit** — **SKIP**

---

## Spec coverage self-check

| Spec requirement | Task |
|---|---|
| Aceternity globe install + `globe.json` | Task 1 |
| Shared RemitX `GlobeDemo`, lazy-load | Task 2 |
| Auth split layout, theme-aware, Clerk retained | Task 3 |
| Marketing landing (hero, 4 beats, trust, footer) | Task 4 |
| Site copy / SEO update | Task 4 |
| Chrome CTAs / hide Sign-in on auth | Task 5 |
| Light/dark + mobile + typecheck verification | Task 6 |
| No commits | All tasks Skip |

## Out of scope (do not implement)

- Quote widget, dashboard, KYC, remittance APIs
- Custom Clerk replacement forms
- Porting fintech transfer/transaction dashboards
