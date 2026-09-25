/**
 * The product graph in the preview, as the Vite plugin built it in Node. The
 * blocks resolve references with the same functions the CLI checks them
 * with (../model.ts), so what renders is what CI accepts.
 */
import graph from "virtual:living-docs/graph"

import type { Doc } from "../model.ts"

export { graph }

export function journeyByTitle(title: string): Doc | undefined {
  return Object.values(graph.docs).find(
    (doc) => doc.kind === "journey" && doc.title === title
  )
}
