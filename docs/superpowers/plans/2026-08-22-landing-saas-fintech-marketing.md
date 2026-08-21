# Landing SaaS-energy marketing Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Refresh `/` into a denser consumer-fintech marketing page using Aceternity feature sections (demo-1 + demo-2), SaaS energy, no gradients.

**Architecture:** Adapt Aceternity demos into `app/components/aceternity/` and thin landing wrappers in `app/components/landing/`. Wire in `home.tsx`. Theme tokens only.

**Tech Stack:** React Router SPA, Tailwind v4, shadcn, Aceternity, Phosphor

## Global Constraints

- No CSS gradients anywhere on the landing refresh
- Consumer “you” copy; Testnet honesty once
- Phosphor icons; no Tabler
- Do not commit unless asked

---

### Task 1: Install / adapt Aceternity feature shells

- [x] Add `features-section-cards.tsx` (from demo-1) with solid `bg-card` / border, keep Grid SVG if non-gradient
- [x] Add `features-section-hover.tsx` (from demo-2) with Phosphor icons + RemitX journey copy
- [x] Fix imports to `~/lib/utils`

### Task 2: Landing sections + home

- [x] Punchier hero (no radial wash)
- [x] Replace HowItWorks / TrustNote with wrappers over the two feature sections
- [x] Add CTA band
- [x] Update `home.tsx` order
- [x] Optional: punchier `site.ts` description

### Task 3: Verify

- [x] `npm run lint` in frontend
- [x] Grep landing for `gradient`
