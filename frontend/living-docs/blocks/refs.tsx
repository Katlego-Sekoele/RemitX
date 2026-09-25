import { Canvas } from "@storybook/addon-docs/blocks"
import { ArrowRightIcon, LinkSimpleIcon } from "@phosphor-icons/react"
import type { ComponentProps, ReactNode } from "react"

import { resolveDoc } from "../model.ts"
import { DocChip, Unresolved } from "./chips.tsx"
import { graph } from "./graph.ts"
import { ComponentRef, OperationRef, TableRef } from "./journey.tsx"

type StoryExport = ComponentProps<typeof Canvas>["of"]

/** A component, linked to its stories; with `story`, rendered live too. */
export function Screen({
  component,
  story,
}: {
  component?: unknown
  story?: StoryExport
}) {
  return (
    <>
      {component !== undefined && (
        <span className="sb-unstyled inline-flex">
          <ComponentRef component={component} />
        </span>
      )}
      {story !== undefined && <Canvas of={story} />}
    </>
  )
}

/**
 * An API operation, by the name the frontend calls it (`quotes.createQuote`)
 * or its operationId. `tables` declares which tables it uses: the one way an
 * operation is tied to the database.
 */
export function Api({
  operation,
  tables,
}: {
  operation: string
  tables?: string | string[]
}) {
  const used =
    tables === undefined ? [] : Array.isArray(tables) ? tables : [tables]
  return (
    <span className="sb-unstyled inline-flex flex-wrap items-center gap-2 align-middle">
      <OperationRef operation={operation} />
      {used.length > 0 && <ArrowRightIcon aria-label="uses" />}
      {used.map((table) => (
        <TableRef key={table} table={table} />
      ))}
    </span>
  )
}

/** A table, or one of its columns. */
export function Database({
  table,
  column,
}: {
  table: string
  column?: string
}) {
  return (
    <span className="sb-unstyled inline-flex align-middle">
      <TableRef table={table} column={column} />
    </span>
  )
}

/** Another journey or concept this one relates to. */
export function RelatedFeature({
  journey,
  concept,
  children,
}: {
  journey?: string
  concept?: string
  children?: ReactNode
}) {
  const ref = journey ?? concept ?? ""
  const doc = resolveDoc(
    graph.docs,
    ref,
    journey !== undefined ? "journey" : "concept"
  )
  return (
    <div className="sb-unstyled my-2 flex flex-wrap items-center gap-2 text-sm">
      <LinkSimpleIcon aria-hidden />
      <span className="text-muted-foreground">Related</span>
      {doc ? <DocChip doc={doc} /> : <Unresolved>{ref}</Unresolved>}
      {children && <span className="text-muted-foreground">{children}</span>}
    </div>
  )
}
