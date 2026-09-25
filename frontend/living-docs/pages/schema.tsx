import { Fragment, type ReactNode } from "react"

import { Badge } from "~/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { schemaRefName, type JsonSchema } from "../model.ts"
import { Prose } from "./text.tsx"

export const schemaAnchor = (name: string) => `schema-${name}`

const asSchemas = (value: unknown) =>
  Array.isArray(value) ? (value as JsonSchema[]) : []

function join(parts: ReactNode[], separator: string) {
  return parts.map((part, i) => (
    <Fragment key={i}>
      {i > 0 && separator}
      {part}
    </Fragment>
  ))
}

/** A schema as a type expression: `QuoteRead`, `string (uuid) | null`, `Item[]`. */
export function TypeLabel({ schema }: { schema?: JsonSchema }): ReactNode {
  if (!schema) return <span>any</span>
  const ref = schemaRefName(schema)
  if (ref) {
    return (
      <a
        href={`#${schemaAnchor(ref)}`}
        className="underline underline-offset-4"
      >
        {ref}
      </a>
    )
  }
  const union = asSchemas(schema.anyOf ?? schema.oneOf)
  if (union.length) {
    return join(
      union.map((part, i) => <TypeLabel key={i} schema={part} />),
      " | "
    )
  }
  const all = asSchemas(schema.allOf)
  if (all.length === 1) return <TypeLabel schema={all[0]} />
  if (Array.isArray(schema.enum)) {
    return <span>{schema.enum.map((v) => JSON.stringify(v)).join(" | ")}</span>
  }
  if (schema.const !== undefined)
    return <span>{JSON.stringify(schema.const)}</span>
  const types = Array.isArray(schema.type) ? schema.type : [schema.type]
  if (types.includes("array")) {
    return (
      <>
        <TypeLabel schema={schema.items as JsonSchema | undefined} />
        []
      </>
    )
  }
  if (types.includes("object") && schema.additionalProperties) {
    const values =
      typeof schema.additionalProperties === "object"
        ? (schema.additionalProperties as JsonSchema)
        : undefined
    return (
      <>
        {"Record<string, "}
        <TypeLabel schema={values} />
        {">"}
      </>
    )
  }
  const name = types.filter(Boolean).join(" | ") || "any"
  return (
    <span>
      {name}
      {typeof schema.format === "string" ? ` (${schema.format})` : ""}
    </span>
  )
}

/** A named schema: its properties, or its values if it is an enum. */
export function SchemaDefinition({
  name,
  schema,
}: {
  name: string
  schema: JsonSchema
}) {
  const properties = Object.entries(
    (schema.properties as Record<string, JsonSchema> | undefined) ?? {}
  )
  const required = new Set(
    Array.isArray(schema.required) ? (schema.required as string[]) : []
  )
  return (
    <section
      id={schemaAnchor(name)}
      className="flex scroll-mt-4 flex-col gap-2"
    >
      <h3 className="flex items-center gap-2 font-mono text-sm font-medium">
        {name}
        {Array.isArray(schema.enum) && <Badge variant="outline">enum</Badge>}
      </h3>
      {typeof schema.description === "string" && (
        <div className="flex flex-col gap-1 text-sm text-muted-foreground">
          <Prose text={schema.description} />
        </div>
      )}
      {Array.isArray(schema.enum) ? (
        <div className="flex flex-wrap gap-2">
          {schema.enum.map((value) => (
            <Badge
              key={String(value)}
              variant="secondary"
              className="font-mono"
            >
              {String(value)}
            </Badge>
          ))}
        </div>
      ) : properties.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Field</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Description</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {properties.map(([field, property]) => (
              <TableRow key={field}>
                <TableCell className="font-mono">
                  {field}
                  {required.has(field) ? "" : "?"}
                </TableCell>
                <TableCell className="font-mono">
                  <TypeLabel schema={property} />
                </TableCell>
                <TableCell className="whitespace-normal text-muted-foreground">
                  {typeof property.description === "string" && (
                    <Prose text={property.description} />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <p className="font-mono text-sm">
          <TypeLabel schema={schema} />
        </p>
      )}
    </section>
  )
}
