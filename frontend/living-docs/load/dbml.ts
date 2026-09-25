/**
 * The database model, read from the DBML that scripts/generate-dbml.sh writes
 * from the migrations. Parsed by @dbml/core, the parser behind the dbdiagram
 * CLI that generated the file.
 */
import {
  CompilerError,
  ModelExporter,
  Parser,
  type NormalizedModel,
} from "@dbml/core"

import {
  tableStoryId,
  type Check,
  type DatabaseModel,
  type DbEnum,
  type Diagnostic,
  type Relationship,
  type RelationshipEnd,
  type Table,
} from "../model.ts"

const DEFAULT_SCHEMA = "public"

function parse(source: string) {
  return new Parser().parse(source, "dbmlv2")
}

function qualify(schema: string | null | undefined, name: string) {
  return !schema || schema === DEFAULT_SCHEMA ? name : `${schema}.${name}`
}

function compilerDiagnostics(error: unknown, file: string): Diagnostic[] {
  const diags =
    error instanceof CompilerError
      ? error.diags
      : [{ message: String(error), location: undefined }]
  return diags.map((diag) => ({
    severity: "error" as const,
    code: "invalid-dbml",
    message: `${file} does not parse: ${diag.message}`,
    location: {
      file,
      line: diag.location?.start.line,
      column: diag.location?.start.column,
    },
  }))
}

export function emptyDatabase(file: string): DatabaseModel {
  return { file, tables: {}, enums: {}, relationships: [] }
}

export function ingestDbml(
  source: string,
  file: string,
  ignoredTables: string[] = []
): { database: DatabaseModel; diagnostics: Diagnostic[] } {
  let model: NormalizedModel
  try {
    model = parse(source).normalize()
  } catch (error) {
    return {
      database: emptyDatabase(file),
      diagnostics: compilerDiagnostics(error, file),
    }
  }

  const schemaName = (schemaId: number) => model.schemas[schemaId]?.name
  const checks = (ids: number[]): Check[] =>
    ids.map((id) => ({
      name: model.checks[id].name ?? undefined,
      expression: model.checks[id].expression,
    }))

  const enums: Record<string, DbEnum> = {}
  for (const item of Object.values(model.enums)) {
    const name = qualify(schemaName(item.schemaId), item.name)
    enums[name] = {
      name,
      note: item.note ?? undefined,
      values: item.valueIds.map((id: number) => ({
        name: model.enumValues[id].name,
        note: model.enumValues[id].note ?? undefined,
      })),
    }
  }

  const tables: Record<string, Table> = {}
  for (const table of Object.values(model.tables)) {
    const name = qualify(schemaName(table.schemaId), table.name)
    if (ignoredTables.includes(name)) continue
    tables[name] = {
      name,
      note: table.note ?? undefined,
      columns: table.fieldIds.map((id: number) => {
        const field = model.fields[id]
        const enumType =
          field.enumId === null ? undefined : model.enums[field.enumId]
        return {
          name: field.name,
          type: field.type.type_name,
          // Unset settings come back undefined, whatever the types say.
          pk: Boolean(field.pk),
          unique: Boolean(field.unique),
          notNull: Boolean(field.not_null),
          increment: Boolean(field.increment),
          default:
            field.dbdefault === undefined
              ? undefined
              : String(field.dbdefault.value),
          note: field.note ?? undefined,
          checks: checks(field.checkIds),
          enum: enumType
            ? qualify(schemaName(enumType.schemaId), enumType.name)
            : undefined,
        }
      }),
      indexes: table.indexIds.map((id: number) => {
        const index = model.indexes[id]
        return {
          name: index.name ?? undefined,
          columns: index.columnIds.map(
            (c: number) => model.indexColumns[c].value
          ),
          unique: index.unique ?? false,
          pk: index.pk ?? false,
          type: index.type ?? undefined,
        }
      }),
      checks: checks(table.checkIds),
      storyId: tableStoryId(name),
    }
  }

  const relationships: Relationship[] = []
  for (const ref of Object.values(model.refs)) {
    const ends: RelationshipEnd[] = ref.endpointIds.map((id: number) => {
      const endpoint = model.endpoints[id]
      return {
        table: qualify(endpoint.schemaName, endpoint.tableName),
        columns: endpoint.fieldNames,
        relation: String(endpoint.relation),
      }
    })
    if (ends.length !== 2) continue
    // The "many" end holds the foreign key. In a one-to-one, db2dbml writes
    // the referenced table first, as it does for every other reference.
    const [first, second] = ends
    const firstHolds =
      first.relation.includes("*") && !second.relation.includes("*")
    relationships.push({
      name: ref.name ?? undefined,
      from: firstHolds ? first : second,
      to: firstHolds ? second : first,
      onDelete: ref.onDelete ?? undefined,
      onUpdate: ref.onUpdate ?? undefined,
    })
  }

  return { database: { file, tables, enums, relationships }, diagnostics: [] }
}

type Sortable = { name?: string | null; expression?: string }

const byName = (a: Sortable, b: Sortable) =>
  (a.name ?? "").localeCompare(b.name ?? "") ||
  (a.expression ?? "").localeCompare(b.expression ?? "")

/**
 * The DBML again, with its unordered parts sorted: db2dbml reads CHECK
 * constraints and a table's foreign keys in whatever order Postgres returns
 * them, which varies between runs. Re-exporting through the same library
 * leaves everything else byte for byte as db2dbml wrote it.
 */
export function canonicalizeDbml(source: string): string {
  const database = parse(source)
  for (const schema of database.schemas) {
    for (const table of schema.tables) {
      table.checks.sort(byName)
      for (const field of table.fields) field.checks.sort(byName)
    }
    schema.refs.sort(byName)
  }
  return ModelExporter.export(database, "dbml", false)
}
