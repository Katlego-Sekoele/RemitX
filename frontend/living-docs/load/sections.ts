/**
 * Which files belong to a section, and the sidebar title Storybook gives
 * each. Both come from Storybook's own functions over the same `stories`
 * entries `.storybook/main.ts` uses, so the ids linked to here are the ids
 * Storybook serves.
 */
import { readdirSync } from "node:fs"
import path from "node:path"
import { normalizeStories } from "storybook/internal/common"
import { userOrAutoTitleFromSpecifier } from "storybook/internal/preview-api"

import {
  resolvePath,
  storiesEntry,
  type LivingDocsConfig,
  type Section,
} from "../config.ts"

export type SectionFile = {
  /** Relative to the repo root. */
  file: string
  absolute: string
  /** As Storybook writes it: relative to frontend/, `./` or `../` first. */
  importPath: string
}

type Specifier = ReturnType<typeof normalizeStories>[number]

const toPosix = (value: string) => value.split(path.sep).join("/")

function walk(directory: string): string[] {
  let entries
  try {
    entries = readdirSync(directory, { withFileTypes: true })
  } catch {
    return []
  }
  return entries.flatMap((entry) => {
    if (entry.name.startsWith(".") || entry.name === "node_modules") return []
    const absolute = path.join(directory, entry.name)
    return entry.isDirectory() ? walk(absolute) : [absolute]
  })
}

export function importPathOf(config: LivingDocsConfig, absolute: string) {
  const relative = toPosix(
    path.relative(resolvePath(config, config.frontend), absolute)
  )
  return relative.startsWith(".") ? relative : `./${relative}`
}

export function readSection(config: LivingDocsConfig, section: Section) {
  const [specifier] = normalizeStories([storiesEntry(config, section)], {
    configDir: resolvePath(config, config.storybookConfigDir),
    workingDir: resolvePath(config, config.frontend),
  })
  const files: SectionFile[] = walk(resolvePath(config, section.directory))
    .map((absolute) => ({
      absolute,
      file: toPosix(path.relative(config.root, absolute)),
      importPath: importPathOf(config, absolute),
    }))
    .filter((item) => specifier.importPathMatcher.test(item.importPath))
    .sort((a, b) => a.file.localeCompare(b.file))
  return { specifier, files }
}

export function storyTitle(
  item: SectionFile,
  specifier: Specifier,
  userTitle?: string
): string {
  const title = userOrAutoTitleFromSpecifier(
    item.importPath,
    specifier,
    userTitle
  )
  if (!title) throw new Error(`${item.file} is not in ${specifier.directory}`)
  return title
}
