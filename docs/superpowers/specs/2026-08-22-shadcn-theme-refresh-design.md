# RemitX shadcn theme refresh — design

**Date:** 2026-08-22
**Status:** Approved for implementation
**Scope:** Color tokens + radius in `frontend/app/app.css` (and button radius so `--radius` applies)

## Decision

Refined **cool slate neutrals + rose primary** (`#d72169`), based on fintech color research:
cool surfaces for trust; singular warm accent for CTAs; distinct destructive.

## Tokens

- Primary (light): `oklch(0.577 0.215 4.71)` = `#D72169`
- Primary (dark): lighter rose `oklch(0.72 0.19 4.71)` so small text clears ~4.5:1 on dark surfaces (intentional a11y trade vs same hex in both modes)
- Neutrals / accent surfaces: hue ~238° (cool slate)
- Ring: primary rose
- Destructive: orange-red ~25° (not rose)
- `--radius`: `0.875rem` (was `0.625rem`)
- `Button`: remove `rounded-none` so theme radius applies
- `THEME_COLOR` in `site.ts`: `#0D171E`

## Non-goals

- Layout redesign, font changes, new semantic success token (can follow later)
- Committing unless requested
