import { Canvas } from "@storybook/addon-docs/blocks"
import {
  ArrowRightIcon,
  GitForkIcon,
  MapTrifoldIcon,
  WarningCircleIcon,
  XCircleIcon,
} from "@phosphor-icons/react"
import {
  createContext,
  useContext,
  type ComponentProps,
  type ReactNode,
} from "react"
import { componentKey } from "virtual:living-docs/components"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  nodeKey,
  resolveDoc,
  resolveOperation,
  resolveStep,
  resolveTable,
  slugify,
  type Diagnostic,
  type Doc,
  type NodeKey,
} from "../model.ts"
import {
  ComponentChip,
  DocChip,
  OperationChip,
  TableChip,
  Unresolved,
} from "./chips.tsx"
import { graph, journeyByTitle } from "./graph.ts"
import { DocLink } from "./link.tsx"

const JourneyContext = createContext<Doc | undefined>(undefined)

/** Story exports, as `import * as Stories from "./x.stories"` gives them. */
type StoryExport = ComponentProps<typeof Canvas>["of"]

const list = (value: string | string[] | undefined) =>
  value === undefined ? [] : Array.isArray(value) ? value : [value]

/** A component a page imports, as the graph knows it. */
export function componentInfo(component: unknown) {
  const key = componentKey(component)
  return key ? graph.components[key] : undefined
}

export function OperationRef({ operation: ref }: { operation: string }) {
  const operation = resolveOperation(graph.api, ref)
  return operation ? (
    <OperationChip operation={operation} />
  ) : (
    <Unresolved>{ref}</Unresolved>
  )
}

export function TableRef({
  table: ref,
  column,
}: {
  table: string
  column?: string
}) {
  const found = resolveTable(graph.database, ref, column)
  if (!found) {
    return <Unresolved>{column ? `${ref}.${column}` : ref}</Unresolved>
  }
  const target: NodeKey = found.column
    ? nodeKey("column", `${found.table.name}.${found.column.name}`)
    : nodeKey("table", found.table.name)
  return <TableChip graph={graph} target={target} />
}

export function ComponentRef({ component }: { component: unknown }) {
  const info = componentInfo(component)
  if (info) return <ComponentChip component={info} />
  const name =
    (component as { displayName?: string; name?: string } | undefined)
      ?.displayName ??
    (component as { name?: string } | undefined)?.name ??
    "component"
  return <Unresolved>{name}</Unresolved>
}

/**
 * A user accomplishing something, step by step. One per page under
 * docs/journeys; see docs/journeys/README.md.
 */
export function Journey({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children?: ReactNode
}) {
  const doc = journeyByTitle(title)
  const problems = doc
    ? graph.diagnostics.filter((d) => d.location?.file === doc.file)
    : []
  const errors = problems.filter((d) => d.severity === "error")
  const warnings = problems.filter((d) => d.severity === "warning")
  return (
    <JourneyContext.Provider value={doc}>
      <section className="my-6 flex flex-col gap-4">
        <Card className="sb-unstyled">
          <CardHeader>
            <CardDescription className="flex items-center gap-1">
              <MapTrifoldIcon aria-hidden /> Journey
            </CardDescription>
            <CardTitle className="font-heading text-xl">{title}</CardTitle>
            {description && (
              <CardDescription className="text-sm">
                {description}
              </CardDescription>
            )}
          </CardHeader>
          {doc && doc.steps.length > 0 && (
            <CardContent>
              <ol className="flex flex-wrap items-center gap-2">
                {doc.steps.map((step, i) => (
                  <li key={step.key} className="flex items-center gap-2">
                    {i > 0 && <ArrowRightIcon aria-hidden />}
                    <DocLink to={{ anchor: slugify(step.title) }}>
                      <Badge variant="outline">{step.number}</Badge>
                      {step.title}
                    </DocLink>
                  </li>
                ))}
              </ol>
            </CardContent>
          )}
          {problems.length > 0 && (
            <CardContent className="flex flex-col gap-2">
              {errors.length > 0 && (
                <Alert variant="destructive">
                  <XCircleIcon aria-hidden />
                  <AlertTitle>
                    {errors.length} broken reference
                    {errors.length === 1 ? "" : "s"} on this page
                  </AlertTitle>
                  <PageProblems diagnostics={errors} />
                </Alert>
              )}
              {warnings.length > 0 && (
                <Alert>
                  <WarningCircleIcon aria-hidden />
                  <AlertTitle>
                    {warnings.length} warning
                    {warnings.length === 1 ? "" : "s"} on this page
                  </AlertTitle>
                  <PageProblems diagnostics={warnings} />
                </Alert>
              )}
            </CardContent>
          )}
        </Card>
        {children}
      </section>
    </JourneyContext.Provider>
  )
}

/** A page's own diagnostics, first few: `docs:check` has the rest. */
function PageProblems({ diagnostics }: { diagnostics: Diagnostic[] }) {
  return (
    <AlertDescription>
      {diagnostics.slice(0, 5).map((d) => (
        <div key={`${d.location?.line}:${d.code}:${d.message}`}>
          {d.location?.line ? `Line ${d.location.line}: ` : ""}
          {d.message}
        </div>
      ))}
      <div>Run npm run docs:check for the full report.</div>
    </AlertDescription>
  )
}

/** One step of a journey: the screen, the API it calls, the tables it touches. */
export function Step({
  title,
  component,
  api,
  tables,
  story,
  children,
}: {
  title: string
  component?: unknown
  api?: string | string[]
  tables?: string | string[]
  story?: StoryExport
  children?: ReactNode
}) {
  const doc = useContext(JourneyContext)
  const step = doc ? resolveStep(doc, title) : undefined
  const operations = list(api)
  const touched = list(tables)
  const rows: [string, ReactNode][] = []
  if (component !== undefined) {
    rows.push(["Screen", <ComponentRef component={component} />])
  }
  if (operations.length) {
    rows.push([
      "API",
      operations.map((ref) => <OperationRef key={ref} operation={ref} />),
    ])
  }
  if (touched.length) {
    rows.push([
      "Database",
      touched.map((ref) => <TableRef key={ref} table={ref} />),
    ])
  }
  return (
    // Only the step's own chrome opts out of the docs styles: its prose
    // (children) reads like the rest of the page.
    <Card id={slugify(title)} className="scroll-mt-4">
      <CardHeader className="sb-unstyled">
        <CardTitle className="flex items-center gap-2 font-heading text-base">
          <Badge variant="outline">{step?.number ?? "–"}</Badge>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {rows.length > 0 && (
          <dl className="sb-unstyled grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2">
            {rows.map(([term, details]) => (
              <div key={term} className="contents">
                <dt className="text-xs text-muted-foreground">{term}</dt>
                <dd className="flex flex-wrap items-center gap-3">{details}</dd>
              </div>
            ))}
          </dl>
        )}
        {children && <div>{children}</div>}
        {story !== undefined && <Canvas of={story} />}
      </CardContent>
    </Card>
  )
}

/** A fork in a journey: each Branch says where an outcome leads. */
export function Decision({
  title,
  children,
}: {
  title: string
  children?: ReactNode
}) {
  return (
    <Card size="sm" className="sb-unstyled">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-base">
          <GitForkIcon aria-hidden />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2">{children}</ul>
      </CardContent>
    </Card>
  )
}

export function Branch({
  label,
  step,
  journey,
  concept,
}: {
  label: string
  step?: string
  journey?: string
  concept?: string
}) {
  const doc = useContext(JourneyContext)
  let target: ReactNode
  if (step !== undefined) {
    const found = doc ? resolveStep(doc, step) : undefined
    target = found ? (
      <DocLink to={{ anchor: slugify(found.title) }}>
        <Badge variant="outline">{found.number}</Badge>
        {found.title}
      </DocLink>
    ) : (
      <Unresolved>{step}</Unresolved>
    )
  } else {
    const ref = journey ?? concept ?? ""
    const found = resolveDoc(
      graph.docs,
      ref,
      journey !== undefined ? "journey" : "concept"
    )
    target = found ? <DocChip doc={found} /> : <Unresolved>{ref}</Unresolved>
  }
  return (
    <li className="flex flex-wrap items-center gap-2">
      <Badge variant="secondary">{label}</Badge>
      <ArrowRightIcon aria-hidden />
      {target}
    </li>
  )
}
