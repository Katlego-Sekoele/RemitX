/**
 * The API model, read from the OpenAPI document FastAPI exports. It keeps
 * what the pages show and nothing is restated by hand: operations by their
 * operationId, and schemas as the spec has them, `$ref`s included.
 */
import {
  clientName,
  operationStoryId,
  type ApiModel,
  type ApiParameter,
  type ApiResponse,
  type Diagnostic,
  type JsonSchema,
  type Operation,
} from "../model.ts"

const METHODS = ["get", "put", "post", "delete", "options", "head", "patch"]

type Spec = {
  info?: { title?: string; version?: string }
  tags?: { name: string; description?: string }[]
  paths?: Record<string, Record<string, unknown>>
  components?: { schemas?: Record<string, JsonSchema> }
  security?: Record<string, unknown>[]
}

type RawOperation = {
  operationId?: string
  tags?: string[]
  summary?: string
  description?: string
  deprecated?: boolean
  security?: Record<string, unknown>[]
  parameters?: RawParameter[]
  requestBody?: RawBody
  responses?: Record<string, RawBody>
}

type RawParameter = {
  name: string
  in: string
  required?: boolean
  description?: string
  schema?: JsonSchema
}

type RawBody = {
  required?: boolean
  description?: string
  content?: Record<string, { schema?: JsonSchema }>
}

function firstContent(body: RawBody | undefined) {
  const [contentType, media] = Object.entries(body?.content ?? {})[0] ?? []
  return contentType ? { contentType, schema: media?.schema } : undefined
}

export function ingestOpenApi(
  spec: Spec,
  file: string
): { api: ApiModel; diagnostics: Diagnostic[] } {
  const diagnostics: Diagnostic[] = []
  const operations: Record<string, Operation> = {}
  const tags: ApiModel["tags"] = {}
  for (const tag of spec.tags ?? []) tags[tag.name] = tag

  for (const [path, item] of Object.entries(spec.paths ?? {})) {
    const shared = (item.parameters as RawParameter[] | undefined) ?? []
    for (const method of METHODS) {
      const raw = item[method] as RawOperation | undefined
      if (!raw) continue
      const where = `${method.toUpperCase()} ${path}`
      if (!raw.operationId) {
        diagnostics.push({
          severity: "error",
          code: "operation-without-id",
          message: `${where} has no operationId, so nothing can reference it.`,
          location: { file },
        })
        continue
      }
      const tag = raw.tags?.[0] ?? "default"
      tags[tag] ??= { name: tag }

      const parameters: ApiParameter[] = [...shared, ...(raw.parameters ?? [])]
        .filter((p) => p && typeof p.name === "string")
        .map((p) => ({
          name: p.name,
          in: p.in,
          required: p.required ?? p.in === "path",
          description: p.description,
          schema: p.schema,
        }))

      const request = firstContent(raw.requestBody)
      const responses: ApiResponse[] = Object.entries(raw.responses ?? {})
        .map(([status, response]) => ({
          status,
          description: response.description,
          ...firstContent(response),
        }))
        .sort((a, b) => a.status.localeCompare(b.status))

      const security = raw.security ?? spec.security ?? []
      operations[raw.operationId] = {
        id: raw.operationId,
        name: clientName(raw.operationId),
        tag,
        method: method.toUpperCase(),
        path,
        summary: raw.summary,
        description: raw.description,
        deprecated: raw.deprecated ?? false,
        auth: [...new Set(security.flatMap((entry) => Object.keys(entry)))],
        parameters,
        requestBody: request && {
          required: raw.requestBody?.required ?? false,
          description: raw.requestBody?.description,
          ...request,
        },
        responses,
        storyId: operationStoryId(tag, raw.operationId),
      }
    }
  }

  return {
    api: {
      title: spec.info?.title ?? "API",
      version: spec.info?.version ?? "",
      file,
      tags,
      operations,
      schemas: spec.components?.schemas ?? {},
    },
    diagnostics,
  }
}
