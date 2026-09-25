/**
 * Reads the living-docs elements out of an MDX page without running it: which
 * primitives it uses, with what props, where, and what it imports. Props have
 * to be static (strings, string arrays, imported identifiers) for the checks
 * to follow them; anything else is reported rather than guessed at.
 */
import { createProcessor } from "@mdx-js/mdx"

import type { Diagnostic, Location } from "../model.ts"

/** Where MDX imports the primitives from; .storybook aliases it. */
export const BLOCKS_MODULE = "@living-docs"

export const PRIMITIVES = [
  "Journey",
  "Step",
  "Decision",
  "Branch",
  "Screen",
  "Api",
  "Database",
  "RelatedFeature",
] as const

export type Primitive = (typeof PRIMITIVES)[number]

export type PropValue =
  | { kind: "string"; value: string }
  | { kind: "strings"; value: string[] }
  | { kind: "boolean"; value: boolean }
  | { kind: "identifier"; name: string }
  | { kind: "member"; object: string; property: string }
  | { kind: "dynamic"; source: string }

export type Element = {
  name: Primitive
  props: Record<string, PropValue>
  location: Location
  /** Primitives nested inside this one, however deep. */
  children: Element[]
}

export type Import = {
  local: string
  source: string
  /** The exported name, `default`, or `*` for a namespace import. */
  imported: string
}

export type ParsedDoc = {
  file: string
  meta: { title?: string; name?: string; id?: string }
  imports: Import[]
  elements: Element[]
  diagnostics: Diagnostic[]
}

// The few mdast and estree shapes read here, typed locally rather than
// through @mdx-js/mdx's transitive type packages.
type EsNode = {
  type: string
  value?: unknown
  name?: string
  computed?: boolean
  object?: EsNode
  property?: EsNode
  elements?: (EsNode | null)[]
  expressions?: EsNode[]
  quasis?: { value: { cooked?: string | null } }[]
  expression?: EsNode
  source?: { value: unknown }
  specifiers?: {
    type: string
    local: { name: string }
    imported?: { name?: string; value?: string }
  }[]
  body?: EsNode[]
}

type MdxAttribute = {
  type: string
  name?: string
  value?: string | null | { value: string; data?: { estree?: EsNode } }
}

type MdxNode = {
  type: string
  name?: string | null
  attributes?: MdxAttribute[]
  children?: MdxNode[]
  position?: { start: { line: number; column: number } }
  data?: { estree?: EsNode }
}

const processor = createProcessor({ format: "mdx" })

function evaluate(node: EsNode | undefined, source: string): PropValue {
  const dynamic = { kind: "dynamic", source } as const
  if (!node) return dynamic
  switch (node.type) {
    case "Literal":
      if (typeof node.value === "string")
        return { kind: "string", value: node.value }
      if (typeof node.value === "boolean")
        return { kind: "boolean", value: node.value }
      return dynamic
    case "TemplateLiteral":
      return node.expressions?.length === 0 && node.quasis?.length === 1
        ? { kind: "string", value: node.quasis[0].value.cooked ?? "" }
        : dynamic
    case "ArrayExpression": {
      const values = (node.elements ?? []).map((item) =>
        item?.type === "Literal" && typeof item.value === "string"
          ? item.value
          : undefined
      )
      return values.every((value) => value !== undefined)
        ? { kind: "strings", value: values as string[] }
        : dynamic
    }
    case "Identifier":
      return { kind: "identifier", name: node.name ?? "" }
    case "MemberExpression":
      return node.object?.type === "Identifier" &&
        node.property?.type === "Identifier" &&
        !node.computed
        ? {
            kind: "member",
            object: node.object.name ?? "",
            property: node.property.name ?? "",
          }
        : dynamic
    default:
      return dynamic
  }
}

function readProps(node: MdxNode) {
  const props: Record<string, PropValue> = {}
  let spread = false
  for (const attribute of node.attributes ?? []) {
    if (attribute.type !== "mdxJsxAttribute" || !attribute.name) {
      spread = true
      continue
    }
    const { value } = attribute
    if (value === null || value === undefined) {
      props[attribute.name] = { kind: "boolean", value: true }
    } else if (typeof value === "string") {
      props[attribute.name] = { kind: "string", value }
    } else {
      const statement = value.data?.estree?.body?.[0]
      props[attribute.name] = evaluate(statement?.expression, value.value)
    }
  }
  return { props, spread }
}

function readImports(program: EsNode | undefined): Import[] {
  const imports: Import[] = []
  for (const statement of program?.body ?? []) {
    if (statement.type !== "ImportDeclaration") continue
    const source = String(statement.source?.value ?? "")
    for (const specifier of statement.specifiers ?? []) {
      imports.push({
        local: specifier.local.name,
        source,
        imported:
          specifier.type === "ImportDefaultSpecifier"
            ? "default"
            : specifier.type === "ImportNamespaceSpecifier"
              ? "*"
              : (specifier.imported?.name ?? specifier.imported?.value ?? ""),
      })
    }
  }
  return imports
}

export function parseDoc(source: string, file: string): ParsedDoc {
  const diagnostics: Diagnostic[] = []
  const parsed: ParsedDoc = {
    file,
    meta: {},
    imports: [],
    elements: [],
    diagnostics,
  }

  let tree: MdxNode
  try {
    tree = processor.parse(source) as unknown as MdxNode
  } catch (error) {
    const { line, column, reason } = error as {
      line?: number
      column?: number
      reason?: string
    }
    diagnostics.push({
      severity: "error",
      code: "invalid-mdx",
      message: `${file} is not valid MDX: ${reason ?? String(error)}`,
      location: { file, line, column },
    })
    return parsed
  }

  const pending: MdxNode[] = []
  for (const node of tree.children ?? []) {
    if (node.type === "mdxjsEsm") {
      parsed.imports.push(...readImports(node.data?.estree))
    } else if (node.type === "mdxJsxFlowElement" && node.name === "Meta") {
      // Storybook only reads a top-level Meta, and so does this.
      const { props } = readProps(node)
      for (const key of ["title", "name", "id"] as const) {
        const prop = props[key]
        if (prop?.kind === "string") parsed.meta[key] = prop.value
      }
    } else {
      pending.push(node)
    }
  }

  // An element named like a primitive is one only if it isn't imported from
  // somewhere else: a page is free to use its own `Step`.
  const shadowed = new Set(
    parsed.imports
      .filter((item) => item.source !== BLOCKS_MODULE)
      .map((item) => item.local)
  )
  const isPrimitive = (name: string | null | undefined): name is Primitive =>
    !!name &&
    (PRIMITIVES as readonly string[]).includes(name) &&
    !shadowed.has(name)

  const locate = (node: MdxNode): Location => ({
    file,
    line: node.position?.start.line,
    column: node.position?.start.column,
  })

  const walk = (nodes: MdxNode[], into: Element[]) => {
    for (const node of nodes) {
      const isElement =
        node.type === "mdxJsxFlowElement" || node.type === "mdxJsxTextElement"
      if (isElement && isPrimitive(node.name)) {
        const { props, spread } = readProps(node)
        const element: Element = {
          name: node.name,
          props,
          location: locate(node),
          children: [],
        }
        if (spread) {
          diagnostics.push({
            severity: "warning",
            code: "dynamic-prop",
            message: `<${node.name}> spreads props, which the checks cannot follow.`,
            location: element.location,
          })
        }
        into.push(element)
        walk(node.children ?? [], element.children)
      } else {
        walk(node.children ?? [], into)
      }
    }
  }
  walk(pending, parsed.elements)
  return parsed
}
