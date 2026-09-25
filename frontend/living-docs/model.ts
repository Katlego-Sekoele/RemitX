/**
 * The product graph: what the living docs know about the product, and how its
 * parts connect. Built in Node from the repo's sources of truth (see
 * load/graph.ts) and handed to the Storybook preview as JSON, so everything
 * here is plain data plus pure functions that run in both places. The CLI's
 * checks and the rendered pages resolve references with the same functions
 * below, so a reference the docs render is exactly one CI accepts.
 */
import { storyNameFromExport, toId } from "storybook/internal/csf"

export type Severity = "error" | "warning"

/** A place in the repo; `file` is relative to the repo root. */
export type Location = { file: string; line?: number; column?: number }

export type Diagnostic = {
  severity: Severity
  /** Stable, greppable identifier, e.g. `unknown-operation`. */
  code: string
  message: string
  location?: Location
}

// --- Nodes ------------------------------------------------------------------

export type NodeKind =
  "doc" | "step" | "component" | "operation" | "table" | "column"

/** `<kind>:<id>`, e.g. `operation:create_quote` or `column:quotes.status`. */
export type NodeKey = `${NodeKind}:${string}`

export const nodeKey = (kind: NodeKind, id: string): NodeKey => `${kind}:${id}`

export function splitKey(key: NodeKey): { kind: NodeKind; id: string } {
  const at = key.indexOf(":")
  return { kind: key.slice(0, at) as NodeKind, id: key.slice(at + 1) }
}

// --- API (from frontend/openapi.json) ---------------------------------------

/** An OpenAPI schema object, kept as the spec has it (`$ref`s included). */
export type JsonSchema = { [key: string]: unknown }

export type ApiParameter = {
  name: string
  in: string
  required: boolean
  description?: string
  schema?: JsonSchema
}

export type ApiResponse = {
  status: string
  description?: string
  contentType?: string
  schema?: JsonSchema
}

export type Operation = {
  /** The spec's operationId, e.g. `create_quote`. */
  id: string
  /** What the generated client calls it: `api.<tag>.<name>`, e.g. `createQuote`. */
  name: string
  tag: string
  method: string
  path: string
  summary?: string
  description?: string
  deprecated: boolean
  /** Security scheme names; empty when the operation needs no session. */
  auth: string[]
  parameters: ApiParameter[]
  requestBody?: {
    required: boolean
    contentType: string
    schema?: JsonSchema
    description?: string
  }
  responses: ApiResponse[]
  storyId: string
}

/** A `$ref` into `components.schemas`, as the schema name it points at. */
export function schemaRefName(schema: JsonSchema | undefined) {
  const ref = schema?.$ref
  return typeof ref === "string"
    ? ref.replace(/^#\/components\/schemas\//, "")
    : undefined
}

/** Every named schema `roots` reach, in the order a reader meets them. */
export function collectSchemas(
  roots: (JsonSchema | undefined)[],
  schemas: Record<string, JsonSchema>
): string[] {
  const seen: string[] = []
  const visit = (value: unknown) => {
    if (!value || typeof value !== "object") return
    if (Array.isArray(value)) return value.forEach(visit)
    const ref = schemaRefName(value as JsonSchema)
    if (ref) {
      if (seen.includes(ref)) return
      seen.push(ref)
      visit(schemas[ref])
      return
    }
    Object.values(value).forEach(visit)
  }
  roots.forEach(visit)
  return seen
}

export type ApiModel = {
  title: string
  version: string
  file: string
  tags: Record<string, { name: string; description?: string }>
  operations: Record<string, Operation>
  schemas: Record<string, JsonSchema>
}

// --- Database (from docs/database/schema.dbml) ------------------------------

export type Check = { name?: string; expression: string }

export type Column = {
  name: string
  type: string
  pk: boolean
  unique: boolean
  notNull: boolean
  increment: boolean
  default?: string
  note?: string
  checks: Check[]
  /** Set when the column's type is one of the schema's enums. */
  enum?: string
}

export type TableIndex = {
  name?: string
  columns: string[]
  unique: boolean
  pk: boolean
  type?: string
}

export type Table = {
  /** Unqualified in `public`, `schema.table` elsewhere. */
  name: string
  note?: string
  columns: Column[]
  indexes: TableIndex[]
  checks: Check[]
  storyId: string
}

export type RelationshipEnd = {
  table: string
  columns: string[]
  /** DBML cardinality of this end: `1`, `0..1`, `*`, `0..*`, `1..*`. */
  relation: string
}

/** A foreign key: `from` holds it, `to` is what it references. */
export type Relationship = {
  name?: string
  from: RelationshipEnd
  to: RelationshipEnd
  onDelete?: string
  onUpdate?: string
}

export type DbEnum = {
  name: string
  note?: string
  values: { name: string; note?: string }[]
}

export type DatabaseModel = {
  file: string
  tables: Record<string, Table>
  enums: Record<string, DbEnum>
  relationships: Relationship[]
}

// --- Docs (MDX under docs/) and components ----------------------------------

export type DocKind = "journey" | "concept" | "page"

export type Step = {
  key: NodeKey
  title: string
  /** 1-based, in page order. */
  number: number
  location: Location
}

export type Decision = {
  title: string
  location: Location
  branches: { label: string; target?: NodeKey; location: Location }[]
}

export type Doc = {
  key: NodeKey
  kind: DocKind
  file: string
  /** What the page is called: the Journey's title, else Meta's. */
  title: string
  /** Its full sidebar title, e.g. `Journeys/Send money`. */
  storyTitle: string
  docsId: string
  description?: string
  /** Where its <Journey> is, for a journey. */
  location?: Location
  steps: Step[]
  decisions: Decision[]
}

export type ComponentInfo = {
  key: NodeKey
  /** The exported name, or `default`. */
  name: string
  file: string
  stories: { id: string; name: string; title: string }[]
}

// --- Links ------------------------------------------------------------------

/**
 * Every connection the docs declare. Nothing is inferred: a table is tied to
 * an operation only because someone wrote `<Api operation=… tables=…>`.
 *
 * - `step`      a journey's step (doc → step)
 * - `shows`     a step's screen (step → component)
 * - `calls`     a step's API call (step → operation)
 * - `touches`   a step's table or column (step → table | column)
 * - `uses`      an operation's table or column (operation → table | column)
 * - `mentions`  a reference in prose outside any step (doc → anything)
 * - `related`   a RelatedFeature (doc → doc)
 * - `branch`    a Decision's outcome (doc → step | doc)
 */
export type LinkKind =
  | "step"
  | "shows"
  | "calls"
  | "touches"
  | "uses"
  | "mentions"
  | "related"
  | "branch"

export type Link = {
  kind: LinkKind
  from: NodeKey
  to: NodeKey
  /** Where the connection is declared. */
  location: Location
  /** The doc or step a `uses` link was declared in. */
  via?: NodeKey
  label?: string
}

export type ProductGraph = {
  api: ApiModel
  database: DatabaseModel
  docs: Record<string, Doc>
  components: Record<string, ComponentInfo>
  links: Link[]
  diagnostics: Diagnostic[]
}

// --- Storybook ids ----------------------------------------------------------

export const API_ROOT = "APIs"
export const DATABASE_ROOT = "Database"

const RESERVED = new Set(
  (
    "await break case catch class const continue debugger default delete do " +
    "else enum export extends false finally for function if import in " +
    "instanceof let new null return static super switch this throw true try " +
    "typeof var void while with yield"
  ).split(" ")
)

/** A name as a valid CSF export: pages are published as named exports. */
export function exportName(name: string): string {
  const cleaned = name.replace(/[^A-Za-z0-9_$]/g, "_")
  return /^[A-Za-z_$]/.test(cleaned) && !RESERVED.has(cleaned)
    ? cleaned
    : `_${cleaned}`
}

export function operationStoryTitle(tag: string): string {
  return [API_ROOT, ...tag.split(".")].join("/")
}

export function operationStoryId(tag: string, operationId: string): string {
  return toId(
    operationStoryTitle(tag),
    storyNameFromExport(exportName(operationId))
  )
}

export function tableExportName(table: string): string {
  return exportName(table)
}

export function tableStoryTitle(table: string): string {
  return `${DATABASE_ROOT}/${table}`
}

export function tableStoryId(table: string): string {
  return toId(
    tableStoryTitle(table),
    storyNameFromExport(tableExportName(table))
  )
}

// --- Reference resolution ---------------------------------------------------

/** snake_case operationId → the client's camelCase name. */
export function clientName(operationId: string): string {
  return operationId.replace(/_+([a-zA-Z0-9])/g, (_, char: string) =>
    char.toUpperCase()
  )
}

/**
 * An API reference, written the way the frontend calls it or the way the spec
 * names it: `quotes.createQuote`, `createQuote`, `quotes.create_quote` or
 * `create_quote`. A tag prefix, when given, has to match.
 */
export function resolveOperation(
  api: ApiModel,
  ref: string
): Operation | undefined {
  const at = ref.lastIndexOf(".")
  const tag = at === -1 ? undefined : ref.slice(0, at)
  const name = at === -1 ? ref : ref.slice(at + 1)
  const operation = Object.values(api.operations).find(
    (op) => op.id === name || op.name === name
  )
  if (!operation || (tag !== undefined && operation.tag !== tag)) return
  return operation
}

export function formatOperationRef(operation: Operation): string {
  return `${operation.tag}.${operation.name}`
}

/**
 * A table (`quotes`) or column (`quotes.status`) reference. A table in a
 * non-public schema is `schema.table`, so a name that is itself a table wins
 * over reading its last segment as a column.
 */
export function resolveTable(
  database: DatabaseModel,
  ref: string,
  column?: string
): { table: Table; column?: Column } | undefined {
  let tableName = ref
  let columnName = column
  if (!database.tables[ref] && column === undefined) {
    const at = ref.lastIndexOf(".")
    if (at !== -1) {
      tableName = ref.slice(0, at)
      columnName = ref.slice(at + 1)
    }
  }
  const table = database.tables[tableName]
  if (!table) return
  if (columnName === undefined) return { table }
  const found = table.columns.find((c) => c.name === columnName)
  return found ? { table, column: found } : undefined
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

/** A journey or concept, by its title or its file name (`send-money`). */
export function resolveDoc(
  docs: Record<string, Doc>,
  ref: string,
  kind?: DocKind
): Doc | undefined {
  const candidates = Object.values(docs).filter(
    (doc) => kind === undefined || doc.kind === kind
  )
  const slug = slugify(ref)
  return (
    candidates.find((doc) => doc.title === ref) ??
    candidates.find((doc) => slugify(doc.title) === slug) ??
    candidates.find(
      (doc) =>
        slugify(doc.file.replace(/^.*\//, "").replace(/\.mdx$/, "")) === slug
    )
  )
}

export function resolveStep(doc: Doc, ref: string): Step | undefined {
  const slug = slugify(ref)
  return (
    doc.steps.find((step) => step.title === ref) ??
    doc.steps.find((step) => slugify(step.title) === slug)
  )
}

// --- Traversal --------------------------------------------------------------

export function linksFrom(graph: ProductGraph, key: NodeKey): Link[] {
  return graph.links.filter((link) => link.from === key)
}

/** Links pointing at `key`; for a table, links at its columns count too. */
export function linksTo(graph: ProductGraph, key: NodeKey): Link[] {
  const { kind, id } = splitKey(key)
  const columnPrefix = kind === "table" ? `column:${id}.` : undefined
  return graph.links.filter(
    (link) =>
      link.to === key ||
      (columnPrefix !== undefined && link.to.startsWith(columnPrefix))
  )
}

/** The doc a step belongs to. */
export function docOfStep(graph: ProductGraph, step: NodeKey): Doc | undefined {
  const file = splitKey(step).id.replace(/#.*$/, "")
  return graph.docs[file]
}

export function findStep(graph: ProductGraph, key: NodeKey): Step | undefined {
  return docOfStep(graph, key)?.steps.find((step) => step.key === key)
}

/** The table a `table:` or `column:` key belongs to. */
export function tableOf(key: NodeKey): string {
  const { kind, id } = splitKey(key)
  return kind === "column" ? id.slice(0, id.lastIndexOf(".")) : id
}

// --- Presentation -----------------------------------------------------------

/** How a node reads in lists, reports and links. */
export function describeNode(
  graph: ProductGraph,
  key: NodeKey
): { label: string; detail?: string } {
  const { kind, id } = splitKey(key)
  switch (kind) {
    case "operation": {
      const op = graph.api.operations[id]
      return op
        ? { label: `${op.method} ${op.path}`, detail: formatOperationRef(op) }
        : { label: id }
    }
    case "component": {
      const component = graph.components[key]
      return { label: component?.name ?? id, detail: component?.file }
    }
    case "doc":
      return { label: graph.docs[id]?.title ?? id, detail: id }
    case "step": {
      const doc = docOfStep(graph, key)
      const step = findStep(graph, key)
      return {
        label: `${doc?.title ?? "?"} › ${step?.title ?? id}`,
        detail: doc?.file,
      }
    }
    default:
      return { label: id }
  }
}

export type Coverage = {
  journeys: number
  steps: number
  operations: { total: number; referenced: number }
  tables: { total: number; referenced: number }
  components: { referenced: number; withStories: number }
}

export function coverage(graph: ProductGraph): Coverage {
  const targets = new Set(graph.links.map((link) => link.to))
  const tableTargets = new Set(
    graph.links
      .filter((link) => /^(table|column):/.test(link.to))
      .map((link) => tableOf(link.to))
  )
  const components = Object.values(graph.components).filter((c) =>
    targets.has(c.key)
  )
  const journeys = Object.values(graph.docs).filter((d) => d.kind === "journey")
  return {
    journeys: journeys.length,
    steps: journeys.reduce((sum, doc) => sum + doc.steps.length, 0),
    operations: {
      total: Object.keys(graph.api.operations).length,
      referenced: Object.keys(graph.api.operations).filter((id) =>
        targets.has(nodeKey("operation", id))
      ).length,
    },
    tables: {
      total: Object.keys(graph.database.tables).length,
      referenced: Object.keys(graph.database.tables).filter((name) =>
        tableTargets.has(name)
      ).length,
    },
    components: {
      referenced: components.length,
      withStories: components.filter((c) => c.stories.length > 0).length,
    },
  }
}
