import { useOf } from "@storybook/addon-docs/blocks"
import { ArrowRightIcon } from "@phosphor-icons/react"
import type { ReactNode } from "react"

import {
  docOfStep,
  findStep,
  linksFrom,
  linksTo,
  splitKey,
  type NodeKey,
} from "../model.ts"
import { DocChip, OperationChip, TableChip } from "./chips.tsx"
import { graph } from "./graph.ts"

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{term}</span>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  )
}

/**
 * Where a component sits in the product: the journey steps that show it, the
 * API they call and the tables they touch. The preview's docs page template
 * adds it under every component's stories.
 */
export function ProductContext() {
  const resolved = useOf("meta")
  if (resolved.type !== "meta") return null
  const storyIds = new Set(Object.keys(resolved.csfFile.stories))
  const component = Object.values(graph.components).find((c) =>
    c.stories.some((story) => storyIds.has(story.id))
  )
  if (!component) return null

  const steps = linksTo(graph, component.key)
    .filter((link) => link.kind === "shows")
    .map((link) => link.from)
  const calls = new Set<NodeKey>()
  const tables = new Set<NodeKey>()
  for (const step of steps) {
    for (const link of linksFrom(graph, step)) {
      if (link.kind === "calls") calls.add(link.to)
      if (link.kind === "touches") tables.add(link.to)
    }
  }
  for (const operation of calls) {
    for (const link of linksFrom(graph, operation)) {
      if (link.kind === "uses") tables.add(link.to)
    }
  }

  return (
    <section className="sb-unstyled my-8 flex flex-col gap-4">
      <h2 className="font-heading text-lg font-semibold">In the product</h2>
      {steps.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No journey shows {component.name} yet.
        </p>
      ) : (
        <>
          <Row term="Used in journeys">
            {steps.map((step) => {
              const doc = docOfStep(graph, step)
              return doc ? (
                <span key={step} className="flex items-center gap-1">
                  <DocChip doc={doc} />
                  <ArrowRightIcon aria-hidden />
                  {findStep(graph, step)?.title}
                </span>
              ) : null
            })}
          </Row>
          {calls.size > 0 && (
            <Row term="Uses APIs">
              {[...calls].map((key) => {
                const operation = graph.api.operations[splitKey(key).id]
                return operation ? (
                  <OperationChip key={key} operation={operation} />
                ) : null
              })}
            </Row>
          )}
          {tables.size > 0 && (
            <Row term="Related database tables">
              {[...tables].map((key) => (
                <TableChip key={key} graph={graph} target={key} />
              ))}
            </Row>
          )}
        </>
      )}
    </section>
  )
}
