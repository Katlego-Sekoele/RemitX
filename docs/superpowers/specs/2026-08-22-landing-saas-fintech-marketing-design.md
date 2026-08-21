# Landing — SaaS-energy consumer fintech marketing

**Date:** 2026-08-22  
**Status:** Approved

## Goal

Make `/` feel like a marketed consumer remittance product (MoneyGram-adjacent energy, SaaS landing density) without sounding like B2B SaaS or inventing enterprise claims.

## Tone

- **You / send / receive** — individuals, not teams or seats
- Benefit-led, confident, slightly hyped headlines
- One quiet honesty line: XRPL Testnet / academic prototype / no real funds
- Avoid developer-tooling or “built for engineers” framing

## Hard constraints

- **No gradients** — no CSS `bg-gradient-*`, radial washes, or gradient card fades (AI-slop marker). Solid theme tokens only (`bg-background`, `bg-card`, `bg-muted`, `bg-primary`, borders)
- Keep existing globe hero split and Magenta primary
- Phosphor icons only (no Tabler)
- Skip Aceternity **demo-3** (bento + cobe) — second globe stack

## Page structure

1. **Hero** — punchy consumer headline + short support + CTAs; remove radial wash; keep globe
2. **Journey** — adapt [features-section-demo-2](https://ui.aceternity.com/components/feature-sections-free) hover grid (4–8 tiles for send flow)
3. **Why RemitX** — adapt features-section-demo-1 card grid **without** gradient fills (solid surfaces + optional non-gradient grid SVG pattern)
4. **CTA band** — flat section, Create account / Sign in
5. **Footer** — keep lean academic disclosure

## Out of scope

- Fake testimonials, logo clouds, pricing tables
- Commits unless requested
