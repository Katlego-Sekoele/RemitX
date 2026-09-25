/**
 * What a change to the API or the schema touches in the docs. It compares two
 * versions of openapi.json and schema.dbml (a git ref's and the working
 * tree's) and follows the links the docs declare back to the journey steps,
 * pages, operations and screens that depend on what changed:
 *
 *   payments.status changed: text → payment_status
 *     🧭 Checkout › Payment
 *     🔌 POST /payments
 *     🖥 PaymentScreen
 *
 * Something removed has nothing left to link to; any page still naming it
 * fails `check` instead.
 */
import {
  collectSchemas,
  describeNode,
  linksFrom,
  linksTo,
  nodeKey,
  splitKey,
  type ApiModel,
  type Column,
  type DatabaseModel,
  type NodeKey,
  type Operation,
  type ProductGraph,
} from "./model.ts"

export type Change = {
  kind: "added" | "removed" | "changed"
  target: NodeKey
  /** What the target is called, even once it is gone from the graph. */
  label: string
  details: string[]
}

const json = (value: unknown) => JSON.stringify(value ?? null)

function operationLabel(op: Operation) {
  return `${op.method} ${op.path}`
}

export function diffApi(before: ApiModel, after: ApiModel): Change[] {
  const changedSchemas = new Set(
    [
      ...new Set([
        ...Object.keys(before.schemas),
        ...Object.keys(after.schemas),
      ]),
    ].filter((name) => json(before.schemas[name]) !== json(after.schemas[name]))
  )
  const schemasOf = (op: Operation, api: ApiModel) =>
    collectSchemas(
      [
        op.requestBody?.schema,
        ...op.parameters.map((p) => p.schema),
        ...op.responses.map((r) => r.schema),
      ],
      api.schemas
    )

  const changes: Change[] = []
  const ids = new Set([
    ...Object.keys(before.operations),
    ...Object.keys(after.operations),
  ])
  for (const id of [...ids].sort()) {
    const old = before.operations[id]
    const now = after.operations[id]
    const target = nodeKey("operation", id)
    if (!old || !now) {
      const op = (now ?? old)!
      changes.push({
        kind: now ? "added" : "removed",
        target,
        label: operationLabel(op),
        details: [],
      })
      continue
    }
    const details: string[] = []
    if (old.method !== now.method || old.path !== now.path) {
      details.push(`${operationLabel(old)} → ${operationLabel(now)}`)
    }
    if (old.tag !== now.tag) details.push(`tag ${old.tag} → ${now.tag}`)
    if (json(old.auth) !== json(now.auth)) details.push("session requirement")
    if (old.deprecated !== now.deprecated) {
      details.push(now.deprecated ? "deprecated" : "no longer deprecated")
    }
    if (json(old.parameters) !== json(now.parameters))
      details.push("parameters")
    if (json(old.requestBody) !== json(now.requestBody))
      details.push("request body")
    const statuses = (op: Operation) =>
      op.responses.map((r) => `${r.status}:${json(r.schema)}`).join(",")
    if (statuses(old) !== statuses(now)) details.push("responses")
    const schemas = new Set([
      ...schemasOf(old, before),
      ...schemasOf(now, after),
    ])
    for (const name of [...schemas].sort()) {
      if (changedSchemas.has(name)) details.push(`schema ${name}`)
    }
    if (details.length) {
      changes.push({
        kind: "changed",
        target,
        label: operationLabel(now),
        details,
      })
    }
  }
  return changes
}

function columnChanges(old: Column, now: Column): string[] {
  const details: string[] = []
  if (old.type !== now.type) details.push(`type ${old.type} → ${now.type}`)
  if (old.notNull !== now.notNull)
    details.push(now.notNull ? "now NOT NULL" : "now nullable")
  if (old.default !== now.default) {
    details.push(`default ${old.default ?? "none"} → ${now.default ?? "none"}`)
  }
  if (old.pk !== now.pk)
    details.push(now.pk ? "now primary key" : "no longer primary key")
  if (old.unique !== now.unique)
    details.push(now.unique ? "now unique" : "no longer unique")
  if (json(old.checks) !== json(now.checks)) details.push("checks")
  return details
}

export function diffDatabase(
  before: DatabaseModel,
  after: DatabaseModel
): Change[] {
  const changes: Change[] = []
  const names = new Set([
    ...Object.keys(before.tables),
    ...Object.keys(after.tables),
  ])
  const keysOf = (db: DatabaseModel, table: string) =>
    new Set(
      db.relationships
        .filter((r) => r.from.table === table)
        .map(
          (r) =>
            `${r.from.columns.join(",")} → ${r.to.table}.${r.to.columns.join(",")}`
        )
    )

  for (const name of [...names].sort()) {
    const old = before.tables[name]
    const now = after.tables[name]
    const target = nodeKey("table", name)
    if (!old || !now) {
      changes.push({
        kind: now ? "added" : "removed",
        target,
        label: name,
        details: [],
      })
      continue
    }
    const columns = new Set([
      ...old.columns.map((c) => c.name),
      ...now.columns.map((c) => c.name),
    ])
    for (const column of columns) {
      const was = old.columns.find((c) => c.name === column)
      const is = now.columns.find((c) => c.name === column)
      const key = nodeKey("column", `${name}.${column}`)
      const label = `${name}.${column}`
      if (!was || !is) {
        changes.push({
          kind: is ? "added" : "removed",
          target: key,
          label,
          details: is ? [is.type] : [],
        })
        continue
      }
      const details = columnChanges(was, is)
      if (details.length)
        changes.push({ kind: "changed", target: key, label, details })
    }

    const tableDetails: string[] = []
    const oldKeys = keysOf(before, name)
    const newKeys = keysOf(after, name)
    for (const key of newKeys)
      if (!oldKeys.has(key)) tableDetails.push(`foreign key ${key} added`)
    for (const key of oldKeys)
      if (!newKeys.has(key)) tableDetails.push(`foreign key ${key} removed`)
    if (json(old.indexes) !== json(now.indexes)) tableDetails.push("indexes")
    if (json(old.checks) !== json(now.checks)) tableDetails.push("checks")
    if (tableDetails.length) {
      changes.push({
        kind: "changed",
        target,
        label: name,
        details: tableDetails,
      })
    }
  }
  return changes
}

export type Affected = {
  steps: NodeKey[]
  docs: NodeKey[]
  operations: NodeKey[]
  components: NodeKey[]
}

/** What the docs connect to `target`, directly or through an operation. */
export function affected(graph: ProductGraph, target: NodeKey): Affected {
  const steps = new Set<NodeKey>()
  const docs = new Set<NodeKey>()
  const operations = new Set<NodeKey>()
  const { kind, id } = splitKey(target)

  // A column's links, and its table's own: an operation declared against the
  // whole table uses every column. Links to sibling columns are not reached.
  const keys = new Set<NodeKey>([target])
  if (kind === "column")
    keys.add(nodeKey("table", id.slice(0, id.lastIndexOf("."))))
  const links =
    kind === "table"
      ? linksTo(graph, target)
      : graph.links.filter((l) => keys.has(l.to))
  for (const link of links) {
    const from = splitKey(link.from).kind
    if (link.kind === "uses" && from === "operation") operations.add(link.from)
    if (from === "step") steps.add(link.from)
    if (from === "doc") docs.add(link.from)
  }
  if (kind === "operation") operations.add(target)
  for (const operation of [...operations]) {
    for (const link of linksTo(graph, operation)) {
      if (splitKey(link.from).kind === "step") steps.add(link.from)
      if (splitKey(link.from).kind === "doc") docs.add(link.from)
    }
  }
  const components = new Set<NodeKey>()
  for (const step of steps) {
    for (const link of linksFrom(graph, step)) {
      if (link.kind === "shows") components.add(link.to)
    }
  }
  operations.delete(target)
  return {
    steps: [...steps],
    docs: [...docs],
    operations: [...operations],
    components: [...components],
  }
}

export type Format = "text" | "markdown"

export function impactReport(
  graph: ProductGraph,
  changes: { api: Change[]; database: Change[] },
  base: string,
  format: Format
): string {
  const md = format === "markdown"
  const lines: string[] = [
    md ? `## Docs impact against \`${base}\`` : `Docs impact against ${base}`,
    "",
  ]
  if (changes.api.length + changes.database.length === 0) {
    lines.push("No API or schema changes.")
    return lines.join("\n") + "\n"
  }
  const code = (text: string) => (md ? `\`${text}\`` : text)
  const section = (title: string, list: Change[]) => {
    if (!list.length) return
    lines.push(md ? `### ${title}` : title, "")
    for (const change of list) {
      const details = change.details.length
        ? `: ${change.details.join(", ")}`
        : ""
      lines.push(
        `${md ? "-" : " "} ${code(change.label)} ${change.kind}${details}`
      )
      if (change.kind === "removed") continue
      const hit = affected(graph, change.target)
      const indent = md ? "  -" : "     "
      for (const step of hit.steps)
        lines.push(`${indent} 🧭 ${describeNode(graph, step).label}`)
      for (const doc of hit.docs)
        lines.push(`${indent} 📄 ${describeNode(graph, doc).label}`)
      for (const op of hit.operations)
        lines.push(`${indent} 🔌 ${describeNode(graph, op).label}`)
      for (const component of hit.components) {
        lines.push(`${indent} 🖥 ${describeNode(graph, component).label}`)
      }
    }
    lines.push("")
  }
  section("Database", changes.database)
  section("API", changes.api)
  return lines.join("\n")
}
