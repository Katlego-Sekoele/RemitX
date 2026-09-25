import {
  CheckCircleIcon,
  MapTrifoldIcon,
  WarningCircleIcon,
  XCircleIcon,
} from "@phosphor-icons/react"
import type { ReactNode } from "react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import { Progress } from "~/components/ui/progress"
import { coverage, type Diagnostic } from "../model.ts"
import { DocChip } from "./chips.tsx"
import { graph } from "./graph.ts"
import { DocLink } from "./link.tsx"

function Tile({
  label,
  value,
  meter,
  children,
}: {
  label: string
  value: ReactNode
  /** A ratio against its limit, e.g. operations referenced of all of them. */
  meter?: { value: number; of: number }
  children?: ReactNode
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl font-semibold">{value}</CardTitle>
      </CardHeader>
      {(meter || children) && (
        <CardContent className="flex flex-col gap-2">
          {meter && meter.of > 0 && (
            <Progress
              value={Math.round((meter.value / meter.of) * 100)}
              aria-label={`${label}: ${meter.value} of ${meter.of}`}
            />
          )}
          {children}
        </CardContent>
      )}
    </Card>
  )
}

/** How much of the product the docs cover, and whether their references hold. */
export function Coverage() {
  const stats = coverage(graph)
  const errors = graph.diagnostics.filter((d) => d.severity === "error").length
  const warnings = graph.diagnostics.length - errors
  return (
    <div className="sb-unstyled my-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <Tile label="Journeys" value={stats.journeys}>
        <CardDescription>{stats.steps} steps</CardDescription>
      </Tile>
      <Tile
        label="API operations referenced"
        value={`${stats.operations.referenced} of ${stats.operations.total}`}
        meter={{
          value: stats.operations.referenced,
          of: stats.operations.total,
        }}
      />
      <Tile
        label="Tables referenced"
        value={`${stats.tables.referenced} of ${stats.tables.total}`}
        meter={{ value: stats.tables.referenced, of: stats.tables.total }}
      />
      <Tile
        label="Screens with stories"
        value={`${stats.components.withStories} of ${stats.components.referenced}`}
        meter={{
          value: stats.components.withStories,
          of: stats.components.referenced,
        }}
      />
      <Tile label="Broken references" value={errors}>
        <CardDescription className="flex items-center gap-1">
          {errors + warnings === 0 ? (
            <>
              <CheckCircleIcon aria-hidden /> Every reference resolves
            </>
          ) : (
            <>
              <WarningCircleIcon aria-hidden />
              {errors} error{errors === 1 ? "" : "s"}, {warnings} warning
              {warnings === 1 ? "" : "s"}
            </>
          )}
        </CardDescription>
      </Tile>
    </div>
  )
}

/** Every journey, for the overview. */
export function JourneyIndex() {
  const journeys = Object.values(graph.docs)
    .filter((doc) => doc.kind === "journey")
    .sort((a, b) => a.title.localeCompare(b.title))
  if (journeys.length === 0) {
    return (
      <Empty className="sb-unstyled my-4">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <MapTrifoldIcon aria-hidden />
          </EmptyMedia>
          <EmptyTitle>No journeys yet</EmptyTitle>
          <EmptyDescription>
            Add one under docs/journeys; docs/journeys/README.md shows how.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <ul className="sb-unstyled my-4 flex flex-col gap-3">
      {journeys.map((doc) => (
        <li key={doc.key} className="flex flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2">
            <DocChip doc={doc} />
            <span className="text-xs text-muted-foreground">
              {doc.steps.length} step{doc.steps.length === 1 ? "" : "s"}
            </span>
          </span>
          {doc.description && (
            <span className="text-sm text-muted-foreground">
              {doc.description}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

function Problem({ diagnostic }: { diagnostic: Diagnostic }) {
  const Icon = diagnostic.severity === "error" ? XCircleIcon : WarningCircleIcon
  const { line, column } = diagnostic.location ?? {}
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon aria-hidden className="mt-0.5 shrink-0" />
      <span>
        <span className="font-medium">
          {diagnostic.severity === "error" ? "Error" : "Warning"}
        </span>
        {line !== undefined && (
          <span className="text-muted-foreground">
            {" "}
            · line {line}
            {column !== undefined ? `:${column}` : ""}
          </span>
        )}
        {" · "}
        {diagnostic.message}{" "}
        <code className="font-mono text-xs text-muted-foreground">
          {diagnostic.code}
        </code>
      </span>
    </li>
  )
}

/** Every reference that does not resolve, by file: what `docs:check` reports. */
export function Health() {
  if (graph.diagnostics.length === 0) {
    return (
      <p className="sb-unstyled my-4 flex items-center gap-2 text-sm">
        <CheckCircleIcon aria-hidden /> Every reference in the docs resolves
        against the API, the schema and the components.
      </p>
    )
  }
  const byFile = new Map<string, Diagnostic[]>()
  for (const diagnostic of graph.diagnostics) {
    const file = diagnostic.location?.file ?? "(no file)"
    byFile.set(file, [...(byFile.get(file) ?? []), diagnostic])
  }
  return (
    <div className="sb-unstyled my-4 flex flex-col gap-4">
      {[...byFile.entries()].map(([file, diagnostics]) => {
        const doc = graph.docs[file]
        return (
          <section key={file} className="flex flex-col gap-2">
            <h3 className="font-mono text-xs font-medium">
              {doc ? <DocLink to={{ docs: doc.docsId }}>{file}</DocLink> : file}
            </h3>
            <ul className="flex flex-col gap-1">
              {diagnostics.map((diagnostic, i) => (
                <Problem key={i} diagnostic={diagnostic} />
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
