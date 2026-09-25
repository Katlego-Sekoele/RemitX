import {
  AppWindowIcon,
  MapTrifoldIcon,
  TableIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react"
import type { ComponentProps, ReactNode } from "react"

import { Badge } from "~/components/ui/badge"
import type {
  ComponentInfo,
  Doc,
  NodeKey,
  Operation,
  ProductGraph,
} from "../model.ts"
import { splitKey, tableOf } from "../model.ts"
import { DocLink } from "./link.tsx"

type BadgeVariant = ComponentProps<typeof Badge>["variant"]

const METHOD_VARIANT: Record<string, BadgeVariant> = {
  GET: "secondary",
  POST: "default",
  PUT: "outline",
  PATCH: "outline",
  DELETE: "destructive",
}

export function MethodBadge({ method }: { method: string }) {
  return (
    <Badge variant={METHOD_VARIANT[method] ?? "outline"} className="font-mono">
      {method}
    </Badge>
  )
}

export function OperationChip({ operation }: { operation: Operation }) {
  return (
    <DocLink to={{ story: operation.storyId }} title={operation.summary}>
      <MethodBadge method={operation.method} />
      <span className="font-mono text-xs">{operation.path}</span>
    </DocLink>
  )
}

/** A table, or a column shown as `table.column`, linking to the table. */
export function TableChip({
  graph,
  target,
}: {
  graph: ProductGraph
  target: NodeKey
}) {
  const table = graph.database.tables[tableOf(target)]
  const label = splitKey(target).id
  if (!table) return <Unresolved>{label}</Unresolved>
  return (
    <DocLink to={{ story: table.storyId }}>
      <TableIcon aria-hidden />
      <span className="font-mono text-xs">{label}</span>
    </DocLink>
  )
}

export function ComponentChip({ component }: { component: ComponentInfo }) {
  const [first] = component.stories
  const content = (
    <>
      <AppWindowIcon aria-hidden />
      <span className="font-medium">{component.name}</span>
    </>
  )
  return first ? (
    <DocLink to={{ story: first.id }} title={component.file}>
      {content}
    </DocLink>
  ) : (
    <span
      className="inline-flex items-center gap-1"
      title={`${component.file} has no stories yet`}
    >
      {content}
    </span>
  )
}

export function DocChip({ doc }: { doc: Doc }) {
  return (
    <DocLink to={{ docs: doc.docsId }}>
      <MapTrifoldIcon aria-hidden />
      <span className="font-medium">{doc.title}</span>
    </DocLink>
  )
}

/** A reference that does not resolve; `npm run docs:check` says why. */
export function Unresolved({ children }: { children: ReactNode }) {
  return (
    <Badge
      variant="destructive"
      title="Unresolved reference: run npm run docs:check"
    >
      <WarningCircleIcon data-icon="inline-start" aria-hidden />
      {children}
    </Badge>
  )
}
