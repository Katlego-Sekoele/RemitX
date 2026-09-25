/**
 * Sidebar entries for the generated sources: one page per API operation,
 * grouped by tag under "APIs", and one per table under "Database". Storybook
 * re-runs these when openapi.json or schema.dbml changes, so the sidebar
 * follows the API and the schema with nothing written by hand. Each entry
 * points at a virtual CSF module that vite-plugin.ts serves.
 */
import { readFileSync } from "node:fs"
import type { Indexer, IndexInput } from "storybook/internal/types"

import { resolvePath, type LivingDocsConfig } from "../config.ts"
import { ingestDbml } from "../load/dbml.ts"
import { ingestOpenApi } from "../load/openapi.ts"
import {
  exportName,
  operationStoryTitle,
  tableExportName,
  tableStoryTitle,
} from "../model.ts"

const TAGS = ["living-docs", "!autodocs", "!test"]

const exactly = (file: string) =>
  new RegExp(`${file.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`)

export function livingDocsIndexers(config: LivingDocsConfig): Indexer[] {
  return [
    {
      test: exactly(resolvePath(config, config.sources.openapi)),
      async createIndex(fileName): Promise<IndexInput[]> {
        const spec = JSON.parse(readFileSync(fileName, "utf8"))
        const { api } = ingestOpenApi(spec, config.sources.openapi)
        return Object.values(api.operations).map((op) => ({
          type: "story",
          importPath: `virtual:living-docs/api/${encodeURIComponent(op.tag)}`,
          exportName: exportName(op.id),
          title: operationStoryTitle(op.tag),
          name: `${op.method} ${op.path}`,
          tags: TAGS,
        }))
      },
    },
    {
      test: exactly(resolvePath(config, config.sources.dbml)),
      async createIndex(fileName): Promise<IndexInput[]> {
        const { database } = ingestDbml(
          readFileSync(fileName, "utf8"),
          config.sources.dbml,
          config.ignoredTables
        )
        return Object.values(database.tables).map((table) => ({
          type: "story",
          importPath: `virtual:living-docs/table/${encodeURIComponent(table.name)}`,
          exportName: tableExportName(table.name),
          title: tableStoryTitle(table.name),
          // Named as its title ends, so the sidebar shows the table as a leaf.
          name: table.name,
          tags: TAGS,
        }))
      },
    },
  ]
}
