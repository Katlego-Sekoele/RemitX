import { KeyIcon } from "@phosphor-icons/react"

import { Badge } from "~/components/ui/badge"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { OperationChip, TableChip, Unresolved } from "../blocks/chips.tsx"
import { graph } from "../blocks/graph.ts"
import {
  linksTo,
  nodeKey,
  splitKey,
  type Link,
  type NodeKey,
  type Relationship,
} from "../model.ts"
import { DocPlace, Nothing, Section } from "./section.tsx"

function endLabel(end: Relationship["from"]) {
  return `${end.table}.${end.columns.join(", ")}`
}

/** A foreign key's far end: its column, linking to its table. */
function EndChip({ end }: { end: Relationship["from"] }) {
  const target =
    end.columns.length === 1
      ? nodeKey("column", `${end.table}.${end.columns[0]}`)
      : nodeKey("table", end.table)
  return (
    <span className="inline-flex items-center gap-1">
      <TableChip graph={graph} target={target} />
      {end.columns.length > 1 && (
        <code className="font-mono text-xs">({end.columns.join(", ")})</code>
      )}
    </span>
  )
}

/** One table, generated from schema.dbml, with what uses it. */
export function TablePage({ table: name }: { table: string }) {
  const table = graph.database.tables[name]
  if (!table) return <Unresolved>{name}</Unresolved>
  const key = nodeKey("table", table.name)

  const outgoing = graph.database.relationships.filter(
    (r) => r.from.table === name
  )
  const incoming = graph.database.relationships.filter(
    (r) => r.to.table === name
  )
  const references = (column: string) =>
    outgoing.filter((r) => r.from.columns.includes(column))

  const links = linksTo(graph, key)
  const operations = links.filter((link) => link.kind === "uses")
  const direct = links.filter(
    (link) => link.kind === "touches" || link.kind === "mentions"
  )
  // Steps that reach this table through an operation that declares it.
  const throughOperations: { step: NodeKey; operation: NodeKey }[] = []
  for (const use of operations) {
    for (const call of linksTo(graph, use.from)) {
      if (call.kind === "calls") {
        throughOperations.push({ step: call.from, operation: use.from })
      }
    }
  }

  const where = (link: Link) =>
    link.to === key ? null : (
      <code className="font-mono text-xs">{splitKey(link.to).id}</code>
    )

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6">
      <PageHeader>
        <PageHeaderDescription>Database</PageHeaderDescription>
        <PageHeaderTitle className="font-mono">{table.name}</PageHeaderTitle>
        {table.note && (
          <PageHeaderDescription>{table.note}</PageHeaderDescription>
        )}
      </PageHeader>

      <Section title="Columns">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Column</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Constraints</TableHead>
              <TableHead>Default</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {table.columns.map((column) => (
              <TableRow key={column.name}>
                <TableCell className="font-mono">
                  <span className="inline-flex items-center gap-1">
                    {column.pk && <KeyIcon aria-label="primary key" />}
                    {column.name}
                  </span>
                </TableCell>
                <TableCell className="font-mono">
                  {column.type}
                  {column.notNull ? "" : " | null"}
                </TableCell>
                <TableCell className="whitespace-normal">
                  <span className="flex flex-wrap items-center gap-1">
                    {column.pk && <Badge variant="default">PK</Badge>}
                    {column.unique && <Badge variant="secondary">unique</Badge>}
                    {column.increment && (
                      <Badge variant="secondary">increment</Badge>
                    )}
                    {references(column.name).map((r) => (
                      <span
                        key={r.name ?? endLabel(r.to)}
                        className="inline-flex items-center gap-1"
                      >
                        <Badge variant="outline">FK</Badge>
                        <EndChip end={r.to} />
                      </span>
                    ))}
                    {column.checks.map((check) => (
                      <code
                        key={check.name ?? check.expression}
                        className="font-mono text-xs text-muted-foreground"
                        title={check.name}
                      >
                        check {check.expression}
                      </code>
                    ))}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-muted-foreground">
                  {column.default ?? ""}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <Section
        title="Relationships"
        description="Foreign keys, from the schema."
      >
        {outgoing.length + incoming.length === 0 && (
          <Nothing>No foreign keys to or from this table.</Nothing>
        )}
        {outgoing.map((r) => (
          <p
            key={`out:${r.name}`}
            className="flex flex-wrap items-center gap-2 text-sm"
          >
            <code className="font-mono text-xs">{endLabel(r.from)}</code>
            references
            <EndChip end={r.to} />
            {r.onDelete && (
              <span className="text-xs text-muted-foreground">
                on delete {r.onDelete}
              </span>
            )}
          </p>
        ))}
        {incoming.map((r) => (
          <p
            key={`in:${r.name}`}
            className="flex flex-wrap items-center gap-2 text-sm"
          >
            <EndChip end={r.from} />
            references
            <code className="font-mono text-xs">{endLabel(r.to)}</code>
          </p>
        ))}
      </Section>

      {(table.indexes.length > 0 || table.checks.length > 0) && (
        <Section title="Indexes and checks">
          {table.indexes.map((index) => (
            <p
              key={index.name ?? index.columns.join(",")}
              className="flex flex-wrap items-center gap-2 text-sm"
            >
              <code className="font-mono text-xs">{index.name ?? "index"}</code>
              on ({index.columns.join(", ")})
              {index.unique && <Badge variant="secondary">unique</Badge>}
            </p>
          ))}
          {table.checks.map((check) => (
            <p key={check.name ?? check.expression} className="text-sm">
              <code className="font-mono text-xs">{check.name ?? "check"}</code>
              : <code className="font-mono text-xs">{check.expression}</code>
            </p>
          ))}
        </Section>
      )}

      <Section
        title="Used by APIs"
        description="Operations the docs declare use this table."
      >
        {operations.length ? (
          <ul className="flex flex-col gap-2">
            {operations.map((link, i) => {
              const operation = graph.api.operations[splitKey(link.from).id]
              return (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  {operation && <OperationChip operation={operation} />}
                  {where(link)}
                  {link.via && (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      declared in <DocPlace place={link.via} />
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        ) : (
          <Nothing>No operation declares this table yet.</Nothing>
        )}
      </Section>

      <Section title="Used by journeys">
        {direct.length + throughOperations.length === 0 && (
          <Nothing>No journey or page references this table yet.</Nothing>
        )}
        <ul className="flex flex-col gap-2">
          {direct.map((link, i) => (
            <li key={`d${i}`} className="flex flex-wrap items-center gap-2">
              <DocPlace place={link.from} />
              {where(link)}
            </li>
          ))}
          {throughOperations.map(({ step, operation }, i) => {
            const op = graph.api.operations[splitKey(operation).id]
            return (
              <li key={`o${i}`} className="flex flex-wrap items-center gap-2">
                <DocPlace place={step} />
                <span className="text-xs text-muted-foreground">through</span>
                {op && <OperationChip operation={op} />}
              </li>
            )
          })}
        </ul>
      </Section>
    </main>
  )
}
