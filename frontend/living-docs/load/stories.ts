/**
 * Component stories: which component each stories file documents, and its
 * story ids. This is what lets a journey's screen link to its stories, and a
 * component's docs page list the journeys it appears in.
 */
import { readFileSync } from "node:fs"
import { loadCsf } from "storybook/internal/csf-tools"

import type { LivingDocsConfig } from "../config.ts"
import {
  nodeKey,
  type ComponentInfo,
  type Diagnostic,
  type NodeKey,
} from "../model.ts"
import { findExport, resolveModule } from "./modules.ts"
import { readSection, storyTitle } from "./sections.ts"

export type StoriesFile = {
  file: string
  importPath: string
  component?: NodeKey
  /** Export name → story id. */
  stories: Record<string, string>
}

type ImportSpecifierNode = {
  type: string
  imported?: { name?: string; value?: string }
}

export function scanStories(config: LivingDocsConfig) {
  const { specifier, files } = readSection(config, config.componentSection)
  const components: Record<string, ComponentInfo> = {}
  const storiesFiles: Record<string, StoriesFile> = {}
  const diagnostics: Diagnostic[] = []

  for (const item of files) {
    let csf
    try {
      csf = loadCsf(readFileSync(item.absolute, "utf8"), {
        fileName: item.importPath,
        makeTitle: (userTitle?: string) =>
          storyTitle(item, specifier, userTitle),
      }).parse()
    } catch (error) {
      diagnostics.push({
        severity: "warning",
        code: "unreadable-stories",
        message: `Could not read ${item.file} as CSF: ${(error as Error).message}`,
        location: { file: item.file },
      })
      continue
    }

    const entry: StoriesFile = {
      file: item.file,
      importPath: item.importPath,
      stories: {},
    }
    for (const input of csf.indexInputs) {
      if (input.exportName && input.__id)
        entry.stories[input.exportName] = input.__id
    }
    storiesFiles[item.file] = entry

    // The component the meta names, traced through its import to a file.
    const rawPath = csf._rawComponentPath
    const specifierNode = csf._componentImportSpecifier as
      ImportSpecifierNode | undefined
    if (!rawPath || !specifierNode) continue
    const imported =
      specifierNode.type === "ImportDefaultSpecifier"
        ? "default"
        : (specifierNode.imported?.name ?? specifierNode.imported?.value)
    const target = resolveModule(config, rawPath, item.file)
    if (!imported || target.kind !== "file") continue
    const origin = findExport(config, target.file, imported)
    if (origin?.kind !== "file") continue

    const key = nodeKey("component", `${origin.file}#${origin.name}`)
    entry.component = key
    const component = (components[key] ??= {
      key,
      name:
        origin.displayName === "default"
          ? String(csf.meta.component ?? "default")
          : origin.displayName,
      file: origin.file,
      stories: [],
    })
    for (const story of csf.stories) {
      component.stories.push({
        id: story.id,
        name: story.name ?? story.id,
        title: csf.meta.title ?? "",
      })
    }
  }
  return { components, storiesFiles, diagnostics }
}
