# Landing page and auth UI — design

**Date:** 2026-08-21
**Status:** Approved, ready for implementation planning
**Scope:** Marketing landing + Clerk sign-in/sign-up presentation

## Problem

RemitX currently shows a placeholder “under construction” home and minimal
Clerk sign-in/sign-up pages on a grid background. The ECO5040W brief requires
a working remittance product story (ZAR → RLUSD on XRPL Testnet) that demos
can open with. Auth already works via Clerk; the gap is product-facing UI.

Reference patterns from
[shadcn-fintech](https://github.com/abderrahimghazali/shadcn-fintech) (split
auth + globe) and Aceternity’s
[GitHub Globe](https://ui.aceternity.com/components/github-globe) inform the
visual approach without replacing Clerk with custom forms.

## Goals

- A marketing landing that explains the remittance journey in one scroll
- Sign-in / sign-up that feel like a remittance product, not a scaffold
- Shared Aceternity globe on landing hero and auth visual panel
- Theme-aware UI (respect light / dark / system via existing theme toggle)
- Stay inside RemitX frontend standards: shadcn + Aceternity, Tailwind for
  layout only, Phosphor icons, existing CSS tokens

## Non-goals

- Interactive FX quote widget or any remittance API wiring
- Dashboard, KYC, beneficiaries, wallet, or admin UI
- Replacing Clerk with custom email/password forms
- Forced dark-mode marketing (theme toggle owns light/dark)
- Committing changes as part of this workstream unless the user asks later

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Landing scope | Marketing only (hero + how-it-works + trust + footer) | Matches brief demo narrative without building product features early |
| Auth pattern | Split layout + Clerk components | Fintech reference layout; keep real auth |
| Globe | Aceternity `@aceternity/globe` | Official registry install; remittance metaphor; reusable |
| Globe placement | Landing hero + auth visual panel | User choice; one wrapper, two consumers |
| Visual tone | Technical prototype with institutional restraint | Mono / ledger language + calm trust cues; existing RemitX palette |
| Theme | Theme tokens everywhere | User feedback: do not hard-code a dark-only landing or auth slab |
| Chrome | Landing top bar CTAs; suppress Sign-in on auth routes | Avoid redundant controls; keep theme toggle |

## Architecture

```
routes/home.tsx
  └─ LandingHero (full-bleed globe + brand + CTAs)
  └─ HowItWorks (4 journey beats; see content section)
  └─ TrustNote
  └─ LandingFooter

routes/sign-in.tsx / sign-up.tsx
  └─ AuthSplitLayout
       ├─ visual panel: logo + GlobeDemo + short line
       └─ form panel: Clerk SignIn / SignUp

components/aceternity/globe.tsx          (CLI install)
components/aceternity/globe-demo.tsx     (RemitX arcs + theme-aware config)
app/data/globe.json                      (Aceternity globe data)
components/auth-split-layout.tsx
```

### Component responsibilities

- **`GlobeDemo`**: configures Aceternity `World` with RemitX-colored arcs
  (e.g. Cape Town–anchored remittance routes). Lazy-loaded; Suspense
  placeholder is a muted panel (no Three.js on the critical path).
- **`AuthSplitLayout`**: `lg+` 50/50 split; `<lg` form-only with compact brand
  above Clerk. Children are the Clerk component only.
- **Landing sections**: compose shadcn `Button`, `Badge`, `Card`/`Separator`
  as needed; Tailwind for section layout only.
- **`AppChrome`**: on landing, prefer a light top bar (wordmark + Get started /
  Sign in) over floating-only controls; on `/sign-in` and `/sign-up`, hide the
  Sign-in CTA; always keep theme toggle.

## Landing content

### Hero (first viewport)

One composition:

1. **RemitX** as the primary brand signal
2. One headline: cross-border ZAR → RLUSD settlement
3. One supporting sentence: XRPL Testnet academic prototype — no real funds
4. CTA group: Get started → `/sign-up`, Sign in → `/sign-in`
5. Dominant full-bleed / background globe (not an inset media card)

No stats strips, feature card grids, or floating promo badges on the hero.

### Below the fold

1. **How it works** — four beats aligned to the brief:
   (1) register & mock KYC,
   (2) quote fees (ZAR → RLUSD),
   (3) confirm ZAR cash-in → async XRPL settlement,
   (4) recipient wallet / simulated cash-out
2. **Built for trust** — short institutional notes: custodial wallet,
   encrypted XRPL keys, queued settlement (not a regulatory essay)
3. **Footer** — RemitX, ECO5040W, testnet disclaimer

### Copy / SEO

Update `SITE_TITLE` and related strings in `app/lib/site.ts` away from
“Coming soon” toward product framing. Landing stays indexable; auth routes
remain `noindex`.

## Auth screens

- Keep `@clerk/react-router` `SignIn` / `SignUp` with existing `shadcn`
  appearance on `ClerkProvider`
- Preserve splat routes (`sign-in/*`, `sign-up/*`) for Clerk multi-step flows
- Cross-links via existing `signUpUrl` / `signInUrl`
- Optional muted academic/testnet note under the form
- Visual panel and form panel use theme tokens (background / muted / border),
  not hard-coded zinc-950

## Dependencies and install

```bash
cd frontend
npx shadcn@latest add @aceternity/globe
```

- Move any CLI output from `frontend/components/` into
  `frontend/app/components/aceternity/`
- Fix imports to `~/lib/utils` and related aliases
- Place `globe.json` at `frontend/app/data/globe.json` (path from Aceternity
  docs / registry)
- Accept transitive Three / R3F / three-globe packages as pulled by the
  registry

## Performance and responsive behaviour

- Lazy-load `GlobeDemo` with `React.lazy` + `Suspense`
- Auth: hide WebGL globe below `lg`; show compact brand mark instead
- Landing: globe remains the hero visual; ensure mobile still reads as one
  composition (brand + headline + CTAs over/around a lighter globe treatment
  if density requires it)

## Error handling

- If WebGL fails or the chunk fails to load, keep Suspense fallback / muted
  panel — never block Clerk or landing CTAs
- Auth and landing must remain usable without the globe

## Testing / verification

- Light and dark theme on landing and both auth routes
- Mobile and desktop layouts
- Clerk email verification / MFA / SSO callback sub-paths still resolve
- `npm run typecheck` and `npm run lint` in `frontend/`

## Useful reference components (later product work)

Not in this spec, but noted from shadcn-fintech for future remittance UI:

- `transfers/*`, `quick-transfer`, `money-movement`
- `transactions/*`, wallet-style balance panels
- `empty-state`, `sidebar`, `tabs`, `dialog`, `select`, `progress`, `avatar`

## Open implementation notes

- Arc endpoints and globe colors should read against RemitX `--primary` /
  `--accent` (or equivalent readable hex samples for Three materials)
- Prefer existing `FadeIn` for section reveals; avoid adding a second motion
  system beyond what Aceternity/Clerk already need
