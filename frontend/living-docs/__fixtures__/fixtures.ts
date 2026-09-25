import { cpSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { defineConfig } from "../config.ts"

const shop = fileURLToPath(new URL("./shop", import.meta.url))

/**
 * A small shop — the brief's Checkout example — laid out like this repo: an
 * OpenAPI spec, a DBML schema, components with stories, and docs. `files`
 * adds or replaces files in a copy, so a test can break one reference.
 */
export function shopFixture(files: Record<string, string> = {}) {
  if (Object.keys(files).length === 0) return defineConfig(shop)
  const root = mkdtempSync(path.join(os.tmpdir(), "living-docs-"))
  cpSync(shop, root, { recursive: true })
  for (const [file, content] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(root, file)), { recursive: true })
    writeFileSync(path.join(root, file), content)
  }
  return defineConfig(root)
}

/** A journey page with the usual imports, wrapping `body`. */
export function journeyPage(body: string, imports = "") {
  return `import { Meta } from "@storybook/addon-docs/blocks"
import { Api, Branch, Database, Decision, Journey, RelatedFeature, Screen, Step } from "@living-docs"
import { Cart } from "~/components/cart"
${imports}

<Meta title="Broken" />

${body}
`
}
