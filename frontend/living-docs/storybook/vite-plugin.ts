/**
 * The Vite side of the addon. It builds the product graph in Node and hands
 * the preview what it needs as virtual modules:
 *
 *   virtual:living-docs/graph        the graph, as JSON
 *   virtual:living-docs/components   component function → graph key
 *   virtual:living-docs/api/<tag>    CSF: one page per operation in <tag>
 *   virtual:living-docs/table/<name> CSF: one table's page
 *
 * The indexers (indexers.ts) point Storybook's sidebar entries at the last
 * two, so the API and database pages are generated, never hand-written.
 * In dev, a change to anything the graph was built from rebuilds it, and the
 * preview reloads if the graph changed.
 */
import path from "node:path"
import { fileURLToPath } from "node:url"
import type { Plugin, ViteDevServer } from "vite"

import { resolvePath, type LivingDocsConfig } from "../config.ts"
import { buildGraph, type GraphBuild } from "../load/graph.ts"
import { exportName, tableExportName } from "../model.ts"

const PREFIX = "virtual:living-docs/"
const RESOLVED = `\0${PREFIX}`

const here = path.dirname(fileURLToPath(import.meta.url))
const pagesDir = path.resolve(here, "../pages")

const PAGE_PARAMETERS = {
  layout: "fullscreen",
  controls: { disable: true },
  actions: { disable: true },
}

const PAGE_TAGS = ["living-docs", "!autodocs", "!test"]

function csfModule(
  component: string,
  file: string,
  stories: { exportName: string; args: Record<string, string> }[]
) {
  const lines = [
    `import { ${component} } from ${JSON.stringify(path.join(pagesDir, file))}`,
    `export default { component: ${component}, parameters: ${JSON.stringify(PAGE_PARAMETERS)}, tags: ${JSON.stringify(PAGE_TAGS)} }`,
    ...stories.map(
      (story) =>
        `export const ${story.exportName} = ${JSON.stringify({ args: story.args })}`
    ),
  ]
  return lines.join("\n")
}

export function livingDocsVitePlugin(config: LivingDocsConfig): Plugin {
  let build: GraphBuild | undefined
  let serialized = ""

  const current = () => {
    if (!build) {
      build = buildGraph(config)
      serialized = JSON.stringify(build.graph)
    }
    return build
  }

  const load = (name: string) => {
    const { graph, componentImports } = current()

    if (name === "graph") {
      return `export default JSON.parse(${JSON.stringify(serialized)})`
    }

    if (name === "components") {
      const imports = componentImports.map(
        (item, i) =>
          `import { ${item.exportName} as c${i} } from ${JSON.stringify(item.specifier)}`
      )
      const entries = componentImports.map(
        (item, i) => `[c${i}, ${JSON.stringify(item.key)}]`
      )
      return [
        ...imports,
        `const keys = new Map([${entries.join(", ")}])`,
        "export function componentKey(component) { return keys.get(component) }",
      ].join("\n")
    }

    if (name.startsWith("api/")) {
      const tag = decodeURIComponent(name.slice("api/".length))
      const operations = Object.values(graph.api.operations).filter(
        (op) => op.tag === tag
      )
      return csfModule(
        "OperationPage",
        "operation-page.tsx",
        operations.map((op) => ({
          exportName: exportName(op.id),
          args: { operationId: op.id },
        }))
      )
    }

    if (name.startsWith("table/")) {
      const table = decodeURIComponent(name.slice("table/".length))
      return csfModule("TablePage", "table-page.tsx", [
        { exportName: tableExportName(table), args: { table } },
      ])
    }
  }

  let server: ViteDevServer | undefined
  let timer: ReturnType<typeof setTimeout> | undefined

  /** Rebuild after a change; reload the preview if the graph moved. */
  const refresh = () => {
    const before = { build, serialized }
    build = undefined
    try {
      current()
    } catch (error) {
      // Mid-edit sources can fail to read; keep the last good graph.
      server?.config.logger.error(`[living-docs] ${(error as Error).message}`)
      ;({ build, serialized } = before)
      return
    }
    if (!server || serialized === before.serialized) return
    const graph = server.environments.client.moduleGraph
    for (const module of graph.idToModuleMap.values()) {
      if (module.id?.startsWith(RESOLVED)) graph.invalidateModule(module)
    }
    server.hot.send({ type: "full-reload" })
  }

  return {
    name: "living-docs",
    enforce: "pre",

    resolveId(id) {
      if (id.startsWith(PREFIX)) return `\0${id}`
    },

    load(id) {
      if (!id.startsWith(RESOLVED)) return
      return load(id.slice(RESOLVED.length))
    },

    configureServer(devServer) {
      server = devServer
      const watched = [
        config.sources.openapi,
        config.sources.dbml,
        config.componentSection.directory,
        ...config.docSections.map((section) => section.directory),
      ].map((file) => resolvePath(config, file))
      devServer.watcher.add(watched)
      devServer.watcher.on("all", (_event, file) => {
        const relevant =
          watched.some(
            (dir) => file === dir || file.startsWith(`${dir}${path.sep}`)
          ) ||
          (build?.inputs.includes(file) ?? false)
        if (!relevant) return
        clearTimeout(timer)
        timer = setTimeout(refresh, 100)
      })
    },
  }
}
