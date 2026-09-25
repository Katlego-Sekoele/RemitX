/**
 * What `cli.ts check` prints: each page's references, resolved (✓) or not
 * (❌ error, ⚠ warning), then problems in the generated sources themselves.
 */
import {
  coverage,
  describeNode,
  splitKey,
  type Diagnostic,
  type Link,
  type LinkKind,
  type NodeKey,
  type ProductGraph,
} from "./model.ts"

export type Format = "text" | "markdown"

const VERBS: Record<LinkKind, string> = {
  step: "has step",
  shows: "shows",
  calls: "calls",
  touches: "touches",
  uses: "uses",
  mentions: "mentions",
  related: "is related to",
  branch: "branches to",
}

const ICON = { ok: "✓", error: "❌", warning: "⚠" } as const

const plural = (count: number, noun: string) =>
  `${count} ${noun}${count === 1 ? "" : "s"}`

function label(graph: ProductGraph, key: NodeKey) {
  const { kind } = splitKey(key)
  const { label, detail } = describeNode(graph, key)
  // A step's page is the heading it is listed under.
  const own = kind === "step" ? label.replace(/^.* › /, "") : label
  return kind === "operation" && detail ? `${own} (${detail})` : own
}

function describeLink(graph: ProductGraph, link: Link) {
  const branch = link.kind === "branch" && link.label ? ` (${link.label})` : ""
  return `${label(graph, link.from)} ${VERBS[link.kind]} ${label(graph, link.to)}${branch}`
}

function where(diagnostic: Diagnostic) {
  const { line, column } = diagnostic.location ?? {}
  return line === undefined ? "" : `${line}:${column ?? 1} `
}

type Entry = { line: number; text: string; icon: keyof typeof ICON }

function pageEntries(graph: ProductGraph, file: string): Entry[] {
  const doc = graph.docs[file]
  const own = new Set<NodeKey>([doc.key, ...doc.steps.map((s) => s.key)])
  const links = graph.links.filter(
    (link) =>
      link.kind !== "step" &&
      (own.has(link.from) || (link.via !== undefined && own.has(link.via)))
  )
  const entries: Entry[] = links.map((link) => ({
    line: link.location.line ?? 0,
    icon: "ok",
    text: describeLink(graph, link),
  }))
  for (const diagnostic of graph.diagnostics) {
    if (diagnostic.location?.file !== file) continue
    entries.push({
      line: diagnostic.location.line ?? 0,
      icon: diagnostic.severity,
      text: `${where(diagnostic)}${diagnostic.message} [${diagnostic.code}]`,
    })
  }
  return entries.sort((a, b) => a.line - b.line)
}

export function counts(graph: ProductGraph) {
  const errors = graph.diagnostics.filter((d) => d.severity === "error").length
  return { errors, warnings: graph.diagnostics.length - errors }
}

export function checkReport(graph: ProductGraph, format: Format): string {
  const md = format === "markdown"
  const lines: string[] = []
  const stats = coverage(graph)
  const pages = Object.values(graph.docs).sort(
    (a, b) => a.kind.localeCompare(b.kind) || a.title.localeCompare(b.title)
  )

  lines.push(
    md ? "## Living docs" : "Living docs",
    "",
    `${plural(stats.journeys, "journey")}, ${plural(stats.steps, "step")} · ` +
      `${stats.operations.referenced}/${stats.operations.total} API operations referenced · ` +
      `${stats.tables.referenced}/${stats.tables.total} tables referenced · ` +
      `${stats.components.withStories}/${stats.components.referenced} referenced components have stories`,
    ""
  )

  for (const doc of pages) {
    const entries = pageEntries(graph, doc.file)
    if (entries.length === 0 && doc.kind === "page") continue
    lines.push(md ? `### ${doc.title}` : `${doc.title}  (${doc.file})`)
    if (md) lines.push("", `\`${doc.file}\``, "")
    if (entries.length === 0)
      lines.push(md ? "- no references" : "  no references")
    for (const entry of entries) {
      const text = md ? entry.text.replace(/\[([\w-]+)\]$/, "`$1`") : entry.text
      lines.push(`${md ? "-" : " "} ${ICON[entry.icon]} ${text}`)
    }
    lines.push("")
  }

  const docFiles = new Set(Object.keys(graph.docs))
  const elsewhere = graph.diagnostics.filter(
    (d) => !d.location || !docFiles.has(d.location.file)
  )
  const sourceErrors = (file: string) =>
    elsewhere.filter((d) => d.location?.file === file).length
  const relationships = graph.database.relationships.length
  lines.push(md ? "### Sources" : "Sources")
  if (md) lines.push("")
  const prefix = md ? "-" : " "
  if (!sourceErrors(graph.api.file)) {
    lines.push(
      `${prefix} ${ICON.ok} ${graph.api.file}: ${Object.keys(graph.api.operations).length} operations`
    )
  }
  if (!sourceErrors(graph.database.file)) {
    lines.push(
      `${prefix} ${ICON.ok} ${graph.database.file}: ${Object.keys(graph.database.tables).length} tables, ${relationships} foreign keys resolve`
    )
  }
  for (const diagnostic of elsewhere) {
    const file = diagnostic.location?.file ? `${diagnostic.location.file} ` : ""
    lines.push(
      `${prefix} ${ICON[diagnostic.severity]} ${file}${where(diagnostic)}${diagnostic.message} [${diagnostic.code}]`
    )
  }

  const { errors, warnings } = counts(graph)
  lines.push(
    "",
    errors || warnings
      ? `${plural(errors, "error")}, ${plural(warnings, "warning")}`
      : "All references resolve."
  )
  return lines.join("\n") + "\n"
}
