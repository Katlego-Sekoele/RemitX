import type { ReactNode } from "react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { DocChip } from "../blocks/chips.tsx"
import { graph } from "../blocks/graph.ts"
import { DocLink } from "../blocks/link.tsx"
import { docOfStep, findStep, splitKey, type NodeKey } from "../model.ts"

export function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: ReactNode
  children: ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-heading text-sm">{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">{children}</CardContent>
    </Card>
  )
}

/** A journey step or docs page, as a link: where a connection was declared. */
export function DocPlace({ place }: { place: NodeKey }) {
  const { kind, id } = splitKey(place)
  if (kind === "doc") {
    const doc = graph.docs[id]
    return doc ? <DocChip doc={doc} /> : <span>{id}</span>
  }
  const doc = docOfStep(graph, place)
  const step = findStep(graph, place)
  if (!doc || !step) return <span>{id}</span>
  return (
    <DocLink to={{ docs: doc.docsId }}>
      <span className="font-medium">{doc.title}</span>
      <span className="text-muted-foreground">› {step.number}.</span>
      {step.title}
    </DocLink>
  )
}

export function Nothing({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>
}
