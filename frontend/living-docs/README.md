# Living docs

A Storybook addon that turns Storybook into a map of how RemitX works:
journeys → screens → API operations → database tables, navigable both ways,
and checked in CI so the docs cannot drift from the code.

Writing docs: [docs/journeys/README.md](../../docs/journeys/README.md). This
file is for working on the addon itself.

## Sources

Everything comes from files the repo already has. Nothing is restated by
hand, and no connection is guessed:

| Source | Made by | Gives |
|---|---|---|
| `frontend/openapi.json` | `cd api && python scripts/export_openapi.py` | operations, schemas, tags |
| `docs/database/schema.dbml` | `scripts/generate-dbml.sh` (dbdiagram CLI) | tables, columns, foreign keys |
| `frontend/app/components/**/*.stories.tsx` | people | components and their story ids |
| `docs/**/*.mdx` | people | journeys, steps, and the links between it all |

Paths and sections live in [config.ts](config.ts), which
`.storybook/main.ts` and the CLI share.

## The graph

[load/graph.ts](load/graph.ts) builds one `ProductGraph`
([model.ts](model.ts)) in Node:

1. [load/openapi.ts](load/openapi.ts) and [load/dbml.ts](load/dbml.ts) read
   the generated sources (DBML through `@dbml/core`, the parser behind the
   CLI that wrote it).
2. [load/stories.ts](load/stories.ts) reads every stories file with
   Storybook's own CSF parser and titles, so the ids it links to are the ids
   Storybook serves, and traces each meta's `component` through
   [load/modules.ts](load/modules.ts) to the file that declares it.
3. [load/mdx.ts](load/mdx.ts) parses each docs page with `@mdx-js/mdx`, without
   running it, into the primitives it uses and their props.
4. Every reference is resolved once. What resolves becomes a `Link`; what
   does not becomes a `Diagnostic`. The link kinds are listed on `LinkKind`
   in model.ts: a table is tied to an operation only by a `uses` link, which
   only `<Api operation tables>` creates.

model.ts is plain data and pure functions (`resolveOperation`,
`resolveTable`, ...) that run in Node and in the browser, so the preview
resolves a reference exactly as the CLI checks it.

## In Storybook

[storybook/preset.ts](storybook/preset.ts) is the addon, listed in
`.storybook/main.ts`:

- **Indexers** ([storybook/indexers.ts](storybook/indexers.ts)) index
  `openapi.json` and `schema.dbml` as if they were story files: one sidebar
  entry per operation (under **APIs**, by tag) and per table (under
  **Database**). Each entry's `importPath` is a virtual module, so Storybook
  re-indexes when the file changes and nobody writes a page by hand.
- **Vite plugin** ([storybook/vite-plugin.ts](storybook/vite-plugin.ts))
  builds the graph and serves `virtual:living-docs/graph` (the graph as
  JSON), `virtual:living-docs/components` (component function → graph key,
  which is how `<Step component={X}>` finds X's stories) and the generated
  CSF modules those entries point at. In dev it rebuilds when a source
  changes and reloads the preview if the graph moved.
- **Aliases**: `@living-docs` → [blocks/index.ts](blocks/index.ts), and `~/`
  for pages under `docs/`, which sit outside the frontend's tsconfig.

[blocks/](blocks/) are the MDX primitives plus `Coverage`, `JourneyIndex`,
`Health` (the Overview page, `docs/index.mdx`) and `ProductContext`, which
`.storybook/preview.tsx` adds to every component's docs page. [pages/](pages/)
are the generated operation and table pages. All of it is shadcn/ui
(`~/components/ui`) with Tailwind for layout.

One thing to know about styling in docs pages: Storybook's docs CSS is not
in a cascade layer, so it beats Tailwind's utilities (which are) on every
`div`, `p`, `code` and so on. Chrome that should look like the app sits under
`.sb-unstyled`; prose an author wrote inside a `Step` must not, or it loses the
docs typography.

## CLI and CI

```bash
node living-docs/cli.ts check [--strict] [--format text|markdown]   # npm run docs:check
node living-docs/cli.ts impact --base origin/main [--format ...]    # npm run docs:impact
node living-docs/cli.ts graph                                      # the graph as JSON
node living-docs/cli.ts canonicalize-dbml <file>                   # used by generate-dbml.sh
```

Node >= 22.18 runs the TypeScript directly (type stripping), which is why
this folder imports with `.ts` extensions and tsconfig sets
`erasableSyntaxOnly`. The `docs` job in `.github/workflows/ci.yml` checks the
OpenAPI spec and the DBML are current, runs `check`, posts `impact` on pull
requests, and builds Storybook.

Tests (`npm test`) build graphs from [__fixtures__/shop](__fixtures__/shop),
a small checkout product laid out like this repo.
