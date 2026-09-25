/**
 * Where the living docs read their sources from. `.storybook/main.ts` and the
 * CLI both use `config`, so the pages Storybook builds and the references CI
 * checks come from the same files. Tests pass their own, rooted at a fixture.
 */
import path from "node:path"
import { fileURLToPath } from "node:url"

import type { DocKind } from "./model.ts"

export type Section = {
  directory: string
  files: string
  titlePrefix?: string
}

export type LivingDocsConfig = {
  /** The repo root; every other path is relative to it. */
  root: string
  frontend: string
  storybookConfigDir: string
  /** Generated sources. Never edit them by hand. */
  sources: { openapi: string; dbml: string }
  /** Written documentation: MDX pages, by the kind each folder holds. */
  docSections: (Section & { kind: DocKind })[]
  /** Component stories: what a journey's screens link to. */
  componentSection: Section
  /** Tables that are bookkeeping, not product schema. */
  ignoredTables: string[]
  /** Import aliases MDX may use, as tsconfig.json's `paths` declares them. */
  importAliases: Record<string, string>
}

export function defineConfig(root: string): LivingDocsConfig {
  return {
    root,
    frontend: "frontend",
    storybookConfigDir: "frontend/.storybook",
    sources: {
      // cd api && python scripts/export_openapi.py
      openapi: "frontend/openapi.json",
      // scripts/generate-dbml.sh
      dbml: "docs/database/schema.dbml",
    },
    docSections: [
      { kind: "page", directory: "docs", files: "*.mdx" },
      {
        kind: "journey",
        directory: "docs/journeys",
        files: "**/*.mdx",
        titlePrefix: "Journeys",
      },
      {
        kind: "concept",
        directory: "docs/concepts",
        files: "**/*.mdx",
        titlePrefix: "Concepts",
      },
    ],
    componentSection: {
      directory: "frontend/app/components",
      files: "**/*.stories.@(ts|tsx)",
      titlePrefix: "Components",
    },
    ignoredTables: ["alembic_version"],
    importAliases: { "~/": "frontend/app/" },
  }
}

/** This repo's. */
export const config = defineConfig(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")
)

export const resolvePath = (config: LivingDocsConfig, file: string) =>
  path.join(config.root, file)

/** A section as a Storybook `stories` entry, relative to `.storybook/`. */
export function storiesEntry(config: LivingDocsConfig, section: Section) {
  return {
    directory: path.relative(
      resolvePath(config, config.storybookConfigDir),
      resolvePath(config, section.directory)
    ),
    files: section.files,
    ...(section.titlePrefix ? { titlePrefix: section.titlePrefix } : {}),
  }
}

/** A generated source as a Storybook `stories` entry: an indexer reads it. */
export function sourceEntry(config: LivingDocsConfig, file: string) {
  return path.relative(
    resolvePath(config, config.storybookConfigDir),
    resolvePath(config, file)
  )
}
