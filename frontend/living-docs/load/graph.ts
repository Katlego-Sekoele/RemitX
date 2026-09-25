/**
 * Builds the product graph from the repo: the API from frontend/openapi.json,
 * the database from docs/database/schema.dbml, component stories, and the MDX
 * pages under docs/. Every reference a page makes is resolved here, once.
 * One that resolves becomes a link; one that doesn't becomes a diagnostic,
 * never a guess. The only connections are the ones pages declare.
 */
import { existsSync, readFileSync } from "node:fs"
import { toId } from "storybook/internal/csf"

import {
  config as repoConfig,
  resolvePath,
  type LivingDocsConfig,
} from "../config.ts"
import {
  formatOperationRef,
  nodeKey,
  resolveDoc,
  resolveOperation,
  resolveStep,
  resolveTable,
  slugify,
  type ApiModel,
  type ComponentInfo,
  type DatabaseModel,
  type Diagnostic,
  type Doc,
  type DocKind,
  type Link,
  type Location,
  type NodeKey,
  type Operation,
  type ProductGraph,
  type Severity,
} from "../model.ts"
import { emptyDatabase, ingestDbml } from "./dbml.ts"
import {
  BLOCKS_MODULE,
  parseDoc,
  type Element,
  type ParsedDoc,
  type Primitive,
  type PropValue,
} from "./mdx.ts"
import { clearModuleCache, findExport, resolveModule } from "./modules.ts"
import { ingestOpenApi } from "./openapi.ts"
import { readSection, storyTitle } from "./sections.ts"
import { scanStories, type StoriesFile } from "./stories.ts"

export type ComponentImport = {
  key: NodeKey
  /** What to import it from: an absolute path, or a package name. */
  specifier: string
  exportName: string
}

export type GraphBuild = {
  graph: ProductGraph
  /** Every file the graph was built from, absolute: what to watch. */
  inputs: string[]
  /** The components pages import, so the preview can map each to its key. */
  componentImports: ComponentImport[]
}

/** The props each primitive takes; anything else is probably a typo. */
const PROPS: Record<Primitive, string[]> = {
  Journey: ["title", "description"],
  Step: ["title", "component", "api", "tables", "story"],
  Decision: ["title"],
  Branch: ["label", "step", "journey", "concept"],
  Screen: ["component", "story"],
  Api: ["operation", "tables"],
  Database: ["table", "column"],
  RelatedFeature: ["journey", "concept"],
}

/** Edit distance, for "did you mean" suggestions. */
function distance(a: string, b: string) {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    let previous = row[0]
    row[0] = i
    for (let j = 1; j <= b.length; j++) {
      const current = row[j]
      row[j] = Math.min(
        row[j] + 1,
        row[j - 1] + 1,
        previous + (a[i - 1] === b[j - 1] ? 0 : 1)
      )
      previous = current
    }
  }
  return row[b.length]
}

function didYouMean(ref: string, candidates: string[]) {
  const limit = Math.max(2, Math.floor(ref.length / 3))
  const close = [...new Set(candidates)]
    .map((name) => ({
      name,
      d: distance(ref.toLowerCase(), name.toLowerCase()),
    }))
    .filter((c) => c.d <= limit)
    .sort((a, b) => a.d - b.d || a.name.localeCompare(b.name))
    .slice(0, 3)
    .map((c) => c.name)
  return close.length ? ` Did you mean ${close.join(", ")}?` : ""
}

type Scope = {
  doc: Doc
  parsed: ParsedDoc
  /** Inside the page's (first) Journey. */
  journey?: boolean
  step?: NodeKey
}

class GraphBuilder {
  readonly links: Link[] = []
  readonly diagnostics: Diagnostic[] = []
  readonly componentImports = new Map<NodeKey, ComponentImport>()
  readonly inputs = new Set<string>()
  readonly docs: Record<string, Doc> = {}
  private readonly warnedWithoutStories = new Set<NodeKey>()

  readonly config: LivingDocsConfig
  readonly api: ApiModel
  readonly database: DatabaseModel
  readonly components: Record<string, ComponentInfo>
  readonly storiesFiles: Record<string, StoriesFile>

  constructor(
    config: LivingDocsConfig,
    api: ApiModel,
    database: DatabaseModel,
    components: Record<string, ComponentInfo>,
    storiesFiles: Record<string, StoriesFile>
  ) {
    this.config = config
    this.api = api
    this.database = database
    this.components = components
    this.storiesFiles = storiesFiles
  }

  report(
    severity: Severity,
    code: string,
    message: string,
    location?: Location
  ) {
    this.diagnostics.push({ severity, code, message, location })
  }

  link(link: Link) {
    const duplicate = this.links.some(
      (other) =>
        other.kind === link.kind &&
        other.from === link.from &&
        other.to === link.to &&
        other.via === link.via &&
        other.label === link.label
    )
    if (!duplicate) this.links.push(link)
  }

  // --- props ----------------------------------------------------------------

  string(element: Element, name: string, required = false) {
    const prop = element.props[name]
    if (prop?.kind === "string") return prop.value
    if (prop) {
      this.report(
        "error",
        "invalid-prop",
        `<${element.name} ${name}> takes a string, e.g. ${name}="…".`,
        element.location
      )
    } else if (required) {
      this.report(
        "error",
        "missing-prop",
        `<${element.name}> needs a ${name}.`,
        element.location
      )
    }
  }

  /** A string prop's value, without reporting; `string()` already did. */
  peek(element: Element, name: string) {
    const prop = element.props[name]
    return prop?.kind === "string" ? prop.value : undefined
  }

  strings(element: Element, name: string): string[] {
    const prop = element.props[name]
    if (!prop) return []
    if (prop.kind === "string") return [prop.value]
    if (prop.kind === "strings") return prop.value
    this.report(
      "error",
      "invalid-prop",
      `<${element.name} ${name}> takes a string or a list of strings, e.g. ${name}={["…"]}.`,
      element.location
    )
    return []
  }

  // --- references -----------------------------------------------------------

  operation(ref: string, location: Location): Operation | undefined {
    const found = resolveOperation(this.api, ref)
    if (found) return found
    const bare = ref.slice(ref.lastIndexOf(".") + 1)
    const untagged = resolveOperation(this.api, bare)
    if (untagged) {
      this.report(
        "error",
        "wrong-tag",
        `${ref}: ${untagged.name} is tagged ${untagged.tag}, so it is ${formatOperationRef(untagged)}.`,
        location
      )
      return
    }
    const names = Object.values(this.api.operations).flatMap((op) => [
      op.name,
      formatOperationRef(op),
    ])
    this.report(
      "error",
      "unknown-operation",
      `No operation ${ref} in ${this.api.file}.${didYouMean(ref, names)}`,
      location
    )
  }

  /** A `table:` or `column:` key, or undefined after reporting why not. */
  table(ref: string, location: Location, column?: string): NodeKey | undefined {
    const found = resolveTable(this.database, ref, column)
    if (found) {
      return found.column
        ? nodeKey("column", `${found.table.name}.${found.column.name}`)
        : nodeKey("table", found.table.name)
    }
    const whole = column === undefined ? ref : `${ref}.${column}`
    const at = whole.lastIndexOf(".")
    const owner =
      at === -1 ? undefined : this.database.tables[whole.slice(0, at)]
    if (owner) {
      const name = whole.slice(at + 1)
      this.report(
        "error",
        "unknown-column",
        `${owner.name} has no column ${name}.${didYouMean(
          name,
          owner.columns.map((c) => c.name)
        )}`,
        location
      )
      return
    }
    this.report(
      "error",
      "unknown-table",
      `No table ${ref} in ${this.database.file}.${didYouMean(
        ref,
        Object.keys(this.database.tables)
      )}`,
      location
    )
  }

  component(scope: Scope, value: PropValue, location: Location) {
    if (value.kind !== "identifier") {
      this.report(
        "error",
        "invalid-prop",
        "component takes an imported component, e.g. component={AmountStep}.",
        location
      )
      return
    }
    const binding = scope.parsed.imports.find((i) => i.local === value.name)
    if (!binding || binding.imported === "*") {
      this.report(
        "error",
        "unknown-component",
        binding
          ? `${value.name} is a namespace import; import the component itself.`
          : `${value.name} is not imported in ${scope.parsed.file}.`,
        location
      )
      return
    }
    const target = resolveModule(this.config, binding.source, scope.parsed.file)
    if (target.kind === "missing") {
      this.report(
        "error",
        "missing-module",
        `Cannot find ${binding.source}, which ${scope.parsed.file} imports ${value.name} from.`,
        location
      )
      return
    }
    if (target.kind === "package") {
      return this.packageComponent(target.name, binding.imported)
    }

    this.inputs.add(resolvePath(this.config, target.file))
    const origin = findExport(this.config, target.file, binding.imported)
    if (!origin) {
      this.report(
        "error",
        "missing-export",
        `${target.file} does not export ${binding.imported}.`,
        location
      )
      return
    }
    if (origin.kind === "package") {
      return this.packageComponent(origin.name, origin.exportName)
    }
    // Keyed by the declaring file, as its stories are: a barrel import is
    // the same component.
    this.inputs.add(resolvePath(this.config, origin.file))
    const key = nodeKey("component", `${origin.file}#${origin.name}`)
    const info = (this.components[key] ??= {
      key,
      name: origin.displayName === "default" ? value.name : origin.displayName,
      file: origin.file,
      stories: [],
    })
    if (info.stories.length === 0 && !this.warnedWithoutStories.has(key)) {
      this.warnedWithoutStories.add(key)
      this.report(
        "warning",
        "component-without-stories",
        `${info.name} (${info.file}) has no stories, so pages cannot link to it.`,
        location
      )
    }
    this.componentImports.set(key, {
      key,
      specifier: resolvePath(this.config, origin.file),
      exportName: origin.name,
    })
    return key
  }

  /** A component from a package: known by name, with no stories here. */
  packageComponent(name: string, exportName: string) {
    const key = nodeKey("component", `${name}#${exportName}`)
    this.components[key] ??= { key, name: exportName, file: name, stories: [] }
    this.componentImports.set(key, { key, specifier: name, exportName })
    return key
  }

  /** `story={Stories.Default}`: returns the component its stories file is for. */
  story(scope: Scope, value: PropValue, location: Location) {
    if (value.kind !== "member") {
      this.report(
        "error",
        "invalid-prop",
        "story takes a story export, e.g. story={AmountStepStories.Default}.",
        location
      )
      return
    }
    const binding = scope.parsed.imports.find(
      (i) => i.local === value.object && i.imported === "*"
    )
    if (!binding) {
      this.report(
        "error",
        "unknown-story",
        `Import the stories file as a namespace: import * as ${value.object} from "./….stories".`,
        location
      )
      return
    }
    if (!binding.source.startsWith(".")) {
      // Storybook only attaches the CSF files a page imports relatively;
      // an aliased import leaves <Canvas> unable to find the story.
      this.report(
        "error",
        "story-import-not-relative",
        `Import ${binding.source} with a relative path: Storybook cannot render stories a page imports through an alias.`,
        location
      )
      return
    }
    const target = resolveModule(this.config, binding.source, scope.parsed.file)
    const storiesFile =
      target.kind === "file" ? this.storiesFiles[target.file] : undefined
    if (!storiesFile) {
      this.report(
        "error",
        "unknown-story",
        `${binding.source} is not a stories file Storybook loads (they live under frontend/app/components).`,
        location
      )
      return
    }
    if (!storiesFile.stories[value.property]) {
      this.report(
        "error",
        "unknown-story",
        `${storiesFile.file} has no story ${value.property}.${didYouMean(
          value.property,
          Object.keys(storiesFile.stories)
        )}`,
        location
      )
      return
    }
    return storiesFile.component
  }

  // --- pages ----------------------------------------------------------------

  /** First pass: the page, its title and steps, so later refs can find them. */
  addDoc(parsed: ParsedDoc, kind: DocKind, title: string, docsId: string) {
    const key = nodeKey("doc", parsed.file)
    const journeys = flatten(parsed.elements).filter(
      (e) => e.name === "Journey"
    )
    const doc: Doc = {
      key,
      kind,
      file: parsed.file,
      title: title.split("/").pop() ?? title,
      storyTitle: title,
      docsId,
      steps: [],
      decisions: [],
    }
    this.docs[parsed.file] = doc

    if (kind !== "journey") {
      for (const journey of journeys) {
        this.report(
          "error",
          "misplaced-journey",
          "A <Journey> belongs in docs/journeys, where the sidebar lists it.",
          journey.location
        )
      }
      return
    }
    if (journeys.length === 0) {
      this.report(
        "warning",
        "missing-journey",
        `${parsed.file} is in docs/journeys but has no <Journey>.`,
        { file: parsed.file }
      )
      return
    }
    for (const extra of journeys.slice(1)) {
      this.report(
        "error",
        "multiple-journeys",
        "One journey per page: move this <Journey> to a page of its own.",
        extra.location
      )
    }

    const journey = journeys[0]
    doc.location = journey.location
    doc.title = this.string(journey, "title", true) ?? doc.title
    doc.description = this.string(journey, "description")
    const seen = new Map<string, Location>()
    for (const step of stepsOf(journey.children)) {
      const stepTitle = this.string(step, "title", true)
      if (!stepTitle) continue
      const slug = slugify(stepTitle)
      if (seen.has(slug)) {
        this.report(
          "error",
          "duplicate-step",
          `${doc.title} already has a step called ${stepTitle}.`,
          step.location
        )
        continue
      }
      seen.set(slug, step.location)
      doc.steps.push({
        key: nodeKey("step", `${parsed.file}#${slug}`),
        title: stepTitle,
        number: doc.steps.length + 1,
        location: step.location,
      })
    }
    if (doc.steps.length === 0) {
      this.report(
        "warning",
        "journey-without-steps",
        `${doc.title} has no steps.`,
        journey.location
      )
    }
  }

  /** Second pass: resolve every reference the page makes. */
  resolveDoc(parsed: ParsedDoc) {
    const doc = this.docs[parsed.file]
    this.checkImports(parsed)
    for (const element of parsed.elements) this.visit({ doc, parsed }, element)
  }

  checkImports(parsed: ParsedDoc) {
    const used = new Map<string, Location>()
    for (const element of flatten(parsed.elements)) {
      if (!used.has(element.name)) used.set(element.name, element.location)
    }
    for (const [name, location] of used) {
      const imported = parsed.imports.some(
        (i) => i.local === name && i.source === BLOCKS_MODULE
      )
      if (!imported) {
        this.report(
          "error",
          "missing-import",
          `<${name}> is used but not imported: import { ${name} } from "${BLOCKS_MODULE}".`,
          location
        )
      }
    }
  }

  visit(scope: Scope, element: Element) {
    for (const prop of Object.keys(element.props)) {
      if (!PROPS[element.name].includes(prop)) {
        this.report(
          "warning",
          "unknown-prop",
          `<${element.name}> has no prop ${prop}; it takes ${PROPS[element.name].join(", ")}.`,
          element.location
        )
      }
    }
    const { doc } = scope
    const from = scope.step ?? doc.key
    const location = element.location

    switch (element.name) {
      case "Journey":
        // Only the first journey counts; addDoc reported any others.
        if (doc.kind === "journey" && !scope.journey) {
          scope = { ...scope, journey: true }
        }
        break
      case "Step": {
        if (scope.step !== undefined) {
          this.report("error", "nested-step", "Steps cannot nest.", location)
          break
        }
        if (!scope.journey) {
          this.report(
            "error",
            "misplaced-step",
            "A <Step> belongs inside a <Journey>.",
            location
          )
          break
        }
        const title = this.peek(element, "title")
        const step = title === undefined ? undefined : resolveStep(doc, title)
        if (!step) break
        scope = { ...scope, step: step.key }
        this.link({ kind: "step", from: doc.key, to: step.key, location })

        let shown: NodeKey | undefined
        if (element.props.component) {
          shown = this.component(scope, element.props.component, location)
          if (shown)
            this.link({ kind: "shows", from: step.key, to: shown, location })
        }
        if (element.props.story) {
          const component = this.story(scope, element.props.story, location)
          // The story's own meta names its component: that is declared, not
          // inferred.
          if (component && !shown) {
            this.link({
              kind: "shows",
              from: step.key,
              to: component,
              location,
            })
          }
        }
        for (const ref of this.strings(element, "api")) {
          const operation = this.operation(ref, location)
          if (operation) {
            this.link({
              kind: "calls",
              from: step.key,
              to: nodeKey("operation", operation.id),
              location,
            })
          }
        }
        for (const ref of this.strings(element, "tables")) {
          const target = this.table(ref, location)
          if (target)
            this.link({ kind: "touches", from: step.key, to: target, location })
        }
        break
      }
      case "Decision": {
        const title = this.string(element, "title", true) ?? ""
        if (doc.kind !== "journey") {
          this.report(
            "error",
            "misplaced-decision",
            "A <Decision> belongs inside a <Journey>.",
            location
          )
        }
        const branches = element.children.filter((c) => c.name === "Branch")
        doc.decisions.push({
          title,
          location,
          branches: branches.map((branch) => ({
            label: this.string(branch, "label", true) ?? "",
            target: this.branchTarget(doc, branch),
            location: branch.location,
          })),
        })
        break
      }
      case "Branch":
        // A Decision checks its own branches; a stray one is an error.
        if (!isBranchOfDecision(scope.parsed, element)) {
          this.report(
            "error",
            "misplaced-branch",
            "A <Branch> belongs inside a <Decision>.",
            location
          )
        }
        break
      case "Screen": {
        const kind = scope.step ? "shows" : "mentions"
        let component: NodeKey | undefined
        if (element.props.component) {
          component = this.component(scope, element.props.component, location)
        }
        if (element.props.story) {
          component ??= this.story(scope, element.props.story, location)
        }
        if (!element.props.component && !element.props.story) {
          this.report(
            "error",
            "missing-prop",
            "<Screen> needs a component or a story.",
            location
          )
        }
        if (component) this.link({ kind, from, to: component, location })
        break
      }
      case "Api": {
        const ref = this.string(element, "operation", true)
        const operation = ref ? this.operation(ref, location) : undefined
        if (!operation) break
        const target = nodeKey("operation", operation.id)
        this.link({
          kind: scope.step ? "calls" : "mentions",
          from,
          to: target,
          location,
        })
        for (const tableRef of this.strings(element, "tables")) {
          const table = this.table(tableRef, location)
          if (table) {
            this.link({
              kind: "uses",
              from: target,
              to: table,
              via: from,
              location,
            })
          }
        }
        break
      }
      case "Database": {
        const ref = this.string(element, "table", true)
        const column = this.string(element, "column")
        const target = ref ? this.table(ref, location, column) : undefined
        if (target) {
          this.link({
            kind: scope.step ? "touches" : "mentions",
            from,
            to: target,
            location,
          })
        }
        break
      }
      case "RelatedFeature": {
        const target = this.docRef(element, location)
        if (target)
          this.link({
            kind: "related",
            from: doc.key,
            to: target.key,
            location,
          })
        break
      }
    }

    for (const child of element.children) this.visit(scope, child)
  }

  docRef(element: Element, location: Location): Doc | undefined {
    const journey = this.string(element, "journey")
    const concept = this.string(element, "concept")
    const ref = journey ?? concept
    if (!ref) {
      this.report(
        "error",
        "missing-prop",
        `<${element.name}> needs a journey or a concept.`,
        location
      )
      return
    }
    const kind = journey !== undefined ? "journey" : "concept"
    const found = resolveDoc(this.docs, ref, kind)
    if (!found) {
      const titles = Object.values(this.docs)
        .filter((doc) => doc.kind === kind)
        .map((doc) => doc.title)
      this.report(
        "error",
        `unknown-${kind}`,
        `No ${kind} called ${ref}.${didYouMean(ref, titles)}`,
        location
      )
    }
    return found
  }

  branchTarget(doc: Doc, branch: Element): NodeKey | undefined {
    const stepRef = this.string(branch, "step")
    if (stepRef !== undefined) {
      const step = resolveStep(doc, stepRef)
      if (!step) {
        this.report(
          "error",
          "unknown-step",
          `${doc.title} has no step ${stepRef}.${didYouMean(
            stepRef,
            doc.steps.map((s) => s.title)
          )}`,
          branch.location
        )
        return
      }
      this.link({
        kind: "branch",
        from: doc.key,
        to: step.key,
        location: branch.location,
        label: this.peek(branch, "label"),
      })
      return step.key
    }
    if (!branch.props.journey && !branch.props.concept) {
      this.report(
        "error",
        "missing-prop",
        "<Branch> needs a step, a journey or a concept to go to.",
        branch.location
      )
      return
    }
    const target = this.docRef(branch, branch.location)
    if (!target) return
    this.link({
      kind: "branch",
      from: doc.key,
      to: target.key,
      location: branch.location,
      label: this.peek(branch, "label"),
    })
    return target.key
  }
}

function flatten(elements: Element[]): Element[] {
  return elements.flatMap((element) => [element, ...flatten(element.children)])
}

/** A journey's steps, not counting any (wrongly) nested in another step. */
function stepsOf(elements: Element[]): Element[] {
  return elements.flatMap((element) =>
    element.name === "Step" ? [element] : stepsOf(element.children)
  )
}

function isBranchOfDecision(parsed: ParsedDoc, branch: Element) {
  return flatten(parsed.elements).some(
    (element) =>
      element.name === "Decision" && element.children.includes(branch)
  )
}

function loadApi(config: LivingDocsConfig): {
  api: ApiModel
  diagnostics: Diagnostic[]
} {
  const file = config.sources.openapi
  const fail = (message: string) => ({
    ...ingestOpenApi({}, file),
    diagnostics: [
      {
        severity: "error" as const,
        code: "missing-source",
        message,
        location: { file },
      },
    ],
  })
  if (!existsSync(resolvePath(config, file))) {
    return fail(
      `${file} is missing. Run: cd api && python scripts/export_openapi.py`
    )
  }
  let spec
  try {
    spec = JSON.parse(readFileSync(resolvePath(config, file), "utf8"))
  } catch (error) {
    return fail(`${file} is not valid JSON: ${(error as Error).message}`)
  }
  return ingestOpenApi(spec, file)
}

function loadDatabase(config: LivingDocsConfig): {
  database: DatabaseModel
  diagnostics: Diagnostic[]
} {
  const file = config.sources.dbml
  if (!existsSync(resolvePath(config, file))) {
    return {
      database: emptyDatabase(file),
      diagnostics: [
        {
          severity: "error",
          code: "missing-source",
          message: `${file} is missing. Run: scripts/generate-dbml.sh`,
          location: { file },
        },
      ],
    }
  }
  return ingestDbml(
    readFileSync(resolvePath(config, file), "utf8"),
    file,
    config.ignoredTables
  )
}

export function buildGraph(config: LivingDocsConfig = repoConfig): GraphBuild {
  clearModuleCache()
  const { api, diagnostics: apiDiagnostics } = loadApi(config)
  const { database, diagnostics: dbDiagnostics } = loadDatabase(config)
  const stories = scanStories(config)

  const builder = new GraphBuilder(
    config,
    api,
    database,
    stories.components,
    stories.storiesFiles
  )
  builder.diagnostics.push(
    ...apiDiagnostics,
    ...dbDiagnostics,
    ...stories.diagnostics
  )
  builder.inputs.add(resolvePath(config, config.sources.openapi))
  builder.inputs.add(resolvePath(config, config.sources.dbml))
  for (const file of Object.keys(stories.storiesFiles)) {
    builder.inputs.add(resolvePath(config, file))
  }

  const parsedDocs: ParsedDoc[] = []
  for (const section of config.docSections) {
    const { specifier, files } = readSection(config, section)
    for (const item of files) {
      builder.inputs.add(item.absolute)
      const parsed = parseDoc(readFileSync(item.absolute, "utf8"), item.file)
      builder.diagnostics.push(...parsed.diagnostics)
      const title = storyTitle(item, specifier, parsed.meta.title)
      const docsId = toId(parsed.meta.id ?? title, parsed.meta.name ?? "Docs")
      builder.addDoc(parsed, section.kind, title, docsId)
      parsedDocs.push(parsed)
    }
  }

  const journeys = Object.values(builder.docs).filter(
    (d) => d.kind === "journey"
  )
  for (const doc of journeys) {
    const others = journeys.filter((d) => d !== doc && d.title === doc.title)
    if (others.length > 0) {
      builder.report(
        "error",
        "duplicate-journey",
        `${others.map((d) => d.file).join(", ")} is also called ${doc.title}; references to it would be ambiguous.`,
        doc.location ?? { file: doc.file }
      )
    }
  }

  for (const parsed of parsedDocs) builder.resolveDoc(parsed)

  return {
    graph: {
      api,
      database,
      docs: builder.docs,
      components: builder.components,
      links: builder.links,
      diagnostics: builder.diagnostics,
    },
    inputs: [...builder.inputs],
    componentImports: [...builder.componentImports.values()],
  }
}
