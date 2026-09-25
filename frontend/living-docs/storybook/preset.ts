/**
 * The living-docs Storybook addon: `.storybook/main.ts` lists this file in
 * `addons`. It adds the indexers that generate the API and database pages,
 * and the Vite plugin that serves them and the product graph.
 */
import path from "node:path"
import { fileURLToPath } from "node:url"
import type { Indexer } from "storybook/internal/types"
import type { InlineConfig } from "vite"

import { config, resolvePath } from "../config.ts"
import { BLOCKS_MODULE } from "../load/mdx.ts"
import { livingDocsIndexers } from "./indexers.ts"
import { livingDocsVitePlugin } from "./vite-plugin.ts"

const blocksEntry = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../blocks/index.ts"
)

export const experimental_indexers = async (existing: Indexer[] = []) => [
  ...livingDocsIndexers(config),
  ...existing,
]

export const viteFinal = async (viteConfig: InlineConfig) => {
  const aliases = [
    { find: new RegExp(`^${BLOCKS_MODULE}$`), replacement: blocksEntry },
    // tsconfig paths only reach files the frontend's tsconfig covers; docs
    // pages live outside it, in docs/.
    ...Object.entries(config.importAliases).map(([prefix, target]) => ({
      find: new RegExp(`^${prefix.replace(/[/]/g, "\\/")}`),
      replacement: `${resolvePath(config, target)}/`,
    })),
  ]
  const existing = viteConfig.resolve?.alias
  return {
    ...viteConfig,
    plugins: [...(viteConfig.plugins ?? []), livingDocsVitePlugin(config)],
    resolve: {
      ...viteConfig.resolve,
      alias: [
        ...aliases,
        ...(Array.isArray(existing)
          ? existing
          : Object.entries(existing ?? {}).map(([find, replacement]) => ({
              find,
              replacement,
            }))),
      ],
      // Docs pages outside frontend/ have no node_modules of their own: these
      // resolve from frontend/ wherever the importing page is.
      dedupe: [
        ...(viteConfig.resolve?.dedupe ?? []),
        "@storybook/addon-docs",
        "react",
        "react-dom",
      ],
    },
    server: {
      ...viteConfig.server,
      fs: {
        ...viteConfig.server?.fs,
        allow: [...(viteConfig.server?.fs?.allow ?? []), config.root],
      },
    },
  }
}
