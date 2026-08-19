# RemitX frontend

React Router v7 SPA + Tailwind v4 + shadcn/ui + Aceternity UI.

```bash
cd frontend
npm ci
npm run dev          # http://localhost:5173
npm run typecheck
npm run format
```

Path alias: `~/*` → `app/*`.

## UI component standard

**Compose UI from shadcn and Aceternity. Use Tailwind/CSS for layout only.**

### shadcn/ui — components and styling

Interactive UI and visual styling for standard elements: buttons, cards, badges, inputs, dialogs, etc.

```bash
npx shadcn@latest add button
npx shadcn@latest add card
```

- Location: `app/components/ui/`
- Import: `import { Button } from "~/components/ui/button"`
- Style via component **variants** and **theme tokens** (`bg-primary`, `text-muted-foreground`, …)
- Do not re-style these with one-off Tailwind color/border/shadow classes unless extending via `className` and `cn()`

### Aceternity UI — effects and motion

Backgrounds, hover spotlight, 3D card tilt, fade-in, and similar stylized effects.

```bash
npx shadcn@latest add @aceternity/3d-card
npx shadcn@latest add @aceternity/grid-background
```

- Registry: `@aceternity` in [components.json](components.json)
- Location: `app/components/aceternity/`
- The CLI may write to `frontend/components/` — **move** files into `app/components/aceternity/` and fix imports to `~/lib/utils`
- Wrap or layer Aceternity effects around shadcn components; do not replace shadcn primitives with raw styled divs

Existing Aceternity components: `3d-card`, `fade-in`, `grid-background`, `spotlight-card`.

### Tailwind / CSS — layout only

Use Tailwind on routes and layout wrappers for structure and spacing:

- Allowed: `flex`, `grid`, `gap`, `items-*`, `justify-*`, `max-w-*`, `w-full`, `px-*`, `py-*`, `min-h-svh`, positioning, responsive breakpoints
- Avoid on leaf UI elements: `bg-*`, `text-*`, `border-*`, `shadow-*`, `rounded-*` when a shadcn or Aceternity component should own that styling

Theme palette and dark mode: [app/app.css](app/app.css). Theme toggle: [app/components/theme-toggle.tsx](app/components/theme-toggle.tsx) (light / dark / auto).

### Icons

Use `@phosphor-icons/react` (configured in `components.json`).

### Example composition

```tsx
// Route: layout with Tailwind; content with shadcn + Aceternity
<GridBackground>
  <main className="flex w-full max-w-lg flex-col gap-6">
    <CardContainer className="w-full">
      <Card>
        <CardHeader>
          <Badge variant="secondary">Under construction</Badge>
          <CardTitle>RemitX</CardTitle>
        </CardHeader>
      </Card>
    </CardContainer>
  </main>
</GridBackground>
```

## Routes

Declare routes in [app/routes.ts](app/routes.ts). Run `npm run typecheck` after adding a route.

### Deep links and Azure Static Web Apps

This is an SPA (`ssr: false`), so the build emits a single `index.html` and
React Router resolves routes in the browser. Azure Static Web Apps serves
files, so without help a request for `/some-route` finds no such file and
returns the platform 404 — the route only works if you navigate to it
client-side from `/`.

[public/staticwebapp.config.json](public/staticwebapp.config.json) fixes that
with a `navigationFallback` rewriting unmatched paths to `/index.html`. Vite
copies `public/` to the build output root, which is the deployed artifact root
(`output_location: build/client`), so the file lands where SWA looks for it.

The `exclude` list keeps real assets out of the fallback: a missing image
should 404, not return an HTML page that the browser then fails to parse as
CSS or JavaScript.

Adding a route needs no change here — the fallback is generic. But if you ever
move `public/` or change `output_location`, make sure that file still ends up
at the artifact root, or every deep link 404s again.

## References

- [CLAUDE.md](../CLAUDE.md) — monorepo overview
- [.cursor/rules/frontend-ui.mdc](../.cursor/rules/frontend-ui.mdc) — AI rule for frontend work
- [shadcn/ui](https://ui.shadcn.com)
- [Aceternity UI](https://ui.aceternity.com)
