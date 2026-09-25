import { LockIcon, LockOpenIcon } from "@phosphor-icons/react"

import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
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
import {
  ComponentChip,
  MethodBadge,
  TableChip,
  Unresolved,
} from "../blocks/chips.tsx"
import { graph } from "../blocks/graph.ts"
import {
  collectSchemas,
  linksFrom,
  linksTo,
  nodeKey,
  type ComponentInfo,
  type NodeKey,
} from "../model.ts"
import { SchemaDefinition, TypeLabel } from "./schema.tsx"
import { DocPlace, Nothing, Section } from "./section.tsx"
import { Prose } from "./text.tsx"

/** One API operation, generated from openapi.json, with what uses it. */
export function OperationPage({ operationId }: { operationId: string }) {
  const operation = graph.api.operations[operationId]
  if (!operation) return <Unresolved>{operationId}</Unresolved>
  const key = nodeKey("operation", operation.id)
  const tag = graph.api.tags[operation.tag]

  const usedBy = linksTo(graph, key).filter(
    (link) => link.kind === "calls" || link.kind === "mentions"
  )
  const screens = new Map<NodeKey, ComponentInfo>()
  for (const link of usedBy) {
    for (const shown of linksFrom(graph, link.from)) {
      const component = graph.components[shown.to]
      if (shown.kind === "shows" && component)
        screens.set(component.key, component)
    }
  }
  const tables = linksFrom(graph, key).filter((link) => link.kind === "uses")

  const errors = operation.responses.filter((r) => /^[45]/.test(r.status))
  const successes = operation.responses.filter((r) => !/^[45]/.test(r.status))
  const schemaNames = collectSchemas(
    [
      operation.requestBody?.schema,
      ...operation.parameters.map((p) => p.schema),
      ...operation.responses.map((r) => r.schema),
    ],
    graph.api.schemas
  )

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6">
      <PageHeader>
        <PageHeaderDescription>
          API › {operation.tag.split(".").join(" › ")}
        </PageHeaderDescription>
        <div className="flex flex-wrap items-center gap-2">
          <MethodBadge method={operation.method} />
          <code className="font-mono text-base">{operation.path}</code>
        </div>
        <PageHeaderTitle>{operation.summary ?? operation.name}</PageHeaderTitle>
        <Prose text={operation.description} paragraph={PageHeaderDescription} />
      </PageHeader>

      <DescriptionList>
        <DescriptionItem>
          <DescriptionTerm>Frontend call</DescriptionTerm>
          <DescriptionDetails className="font-mono">
            api.{operation.tag}.{operation.name}()
          </DescriptionDetails>
        </DescriptionItem>
        <DescriptionItem>
          <DescriptionTerm>operationId</DescriptionTerm>
          <DescriptionDetails className="font-mono">
            {operation.id}
          </DescriptionDetails>
        </DescriptionItem>
        <DescriptionItem>
          <DescriptionTerm>Session</DescriptionTerm>
          <DescriptionDetails className="flex items-center gap-1">
            {operation.auth.length ? (
              <>
                <LockIcon aria-hidden /> Required ({operation.auth.join(", ")})
              </>
            ) : (
              <>
                <LockOpenIcon aria-hidden /> Not required
              </>
            )}
          </DescriptionDetails>
        </DescriptionItem>
        {tag?.description && (
          <DescriptionItem>
            <DescriptionTerm>{operation.tag}</DescriptionTerm>
            <DescriptionDetails>
              <Prose text={tag.description} />
            </DescriptionDetails>
          </DescriptionItem>
        )}
      </DescriptionList>

      <Section
        title="Used by"
        description="Journey steps that call this operation, and pages that mention it."
      >
        {usedBy.length ? (
          <ul className="flex flex-col gap-2">
            {usedBy.map((link, i) => (
              <li key={i}>
                <DocPlace place={link.from} />
              </li>
            ))}
          </ul>
        ) : (
          <Nothing>No journey or page references this operation yet.</Nothing>
        )}
        {screens.size > 0 && (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs text-muted-foreground">Screens</span>
            {[...screens.values()].map((component) => (
              <ComponentChip key={component.key} component={component} />
            ))}
          </div>
        )}
      </Section>

      <Section
        title="Database"
        description={
          <>
            Tables this operation uses, as the docs declare with{" "}
            <code className="font-mono">{"<Api operation tables>"}</code>.
          </>
        }
      >
        {tables.length ? (
          <ul className="flex flex-col gap-2">
            {tables.map((link, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <TableChip graph={graph} target={link.to} />
                {link.via && (
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    declared in <DocPlace place={link.via} />
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <Nothing>No tables declared for this operation.</Nothing>
        )}
      </Section>

      {operation.parameters.length > 0 && (
        <Section title="Parameters">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>In</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Description</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {operation.parameters.map((parameter) => (
                <TableRow key={`${parameter.in}:${parameter.name}`}>
                  <TableCell className="font-mono">
                    {parameter.name}
                    {parameter.required ? "" : "?"}
                  </TableCell>
                  <TableCell>{parameter.in}</TableCell>
                  <TableCell className="font-mono">
                    <TypeLabel schema={parameter.schema} />
                  </TableCell>
                  <TableCell className="whitespace-normal text-muted-foreground">
                    <Prose text={parameter.description} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}

      {operation.requestBody && (
        <Section
          title="Request body"
          description={`${operation.requestBody.contentType}${
            operation.requestBody.required ? ", required" : ", optional"
          }`}
        >
          <p className="font-mono text-sm">
            <TypeLabel schema={operation.requestBody.schema} />
          </p>
        </Section>
      )}

      <Section title="Responses">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Status</TableHead>
              <TableHead>Body</TableHead>
              <TableHead>Description</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...successes, ...errors].map((response) => (
              <TableRow key={response.status}>
                <TableCell className="font-mono">{response.status}</TableCell>
                <TableCell className="font-mono">
                  {response.schema ? (
                    <TypeLabel schema={response.schema} />
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="whitespace-normal text-muted-foreground">
                  <Prose text={response.description} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      {schemaNames.length > 0 && (
        <Section title="Schemas">
          {schemaNames.map((name) => (
            <SchemaDefinition
              key={name}
              name={name}
              schema={graph.api.schemas[name] ?? {}}
            />
          ))}
        </Section>
      )}
    </main>
  )
}
