/**
 * Just enough module resolution to check a docs import points at real code:
 * the `~/` alias and relative paths to a file, and where that file's export
 * is really declared, read with the TypeScript parser rather than by running
 * it. A component is keyed by the file that declares it, so one imported
 * through a barrel file is the same component its stories document.
 */
import { existsSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import ts from "typescript"

import { resolvePath, type LivingDocsConfig } from "../config.ts"

const EXTENSIONS = [".tsx", ".ts", ".jsx", ".js", ".mjs"]

export type ResolvedModule =
  | { kind: "file"; file: string }
  | { kind: "package"; name: string }
  | { kind: "missing"; specifier: string }

const isFile = (candidate: string) =>
  existsSync(candidate) && statSync(candidate).isFile()

/** `from` and the result's `file` are relative to the repo root. */
export function resolveModule(
  config: LivingDocsConfig,
  specifier: string,
  from: string
): ResolvedModule {
  let base: string | undefined
  for (const [prefix, target] of Object.entries(config.importAliases)) {
    if (specifier.startsWith(prefix)) {
      base = path.join(
        resolvePath(config, target),
        specifier.slice(prefix.length)
      )
    }
  }
  if (!base && /^\.\.?(\/|$)/.test(specifier)) {
    base = path.resolve(config.root, path.dirname(from), specifier)
  }
  if (!base) return { kind: "package", name: specifier }

  const candidates = [
    base,
    ...EXTENSIONS.map((ext) => base + ext),
    ...EXTENSIONS.map((ext) => path.join(base, `index${ext}`)),
  ]
  const found = candidates.find(isFile)
  return found
    ? {
        kind: "file",
        file: path.relative(config.root, found).split(path.sep).join("/"),
      }
    : { kind: "missing", specifier }
}

/** A module's exports as written, before following any of them. */
type ModuleShape = {
  /** Names it declares and exports itself (`default` included). */
  declared: Set<string>
  /** What its default export calls itself, when it says. */
  defaultName?: string
  /** `export { local as name }`, for names bound locally. */
  local: Map<string, string>
  /** `export { imported as name } from "specifier"`. */
  reexported: Map<string, { specifier: string; imported: string }>
  /** `export * from "specifier"`. */
  stars: string[]
  /** What the module imports: local name → where from. */
  imports: Map<string, { specifier: string; imported: string }>
}

const shapes = new Map<string, ModuleShape>()

/** Forget what files export; a rebuild after an edit starts from here. */
export function clearModuleCache() {
  shapes.clear()
}

function hasModifier(node: ts.Node, kind: ts.SyntaxKind) {
  return (
    ts.canHaveModifiers(node) &&
    (ts.getModifiers(node) ?? []).some((modifier) => modifier.kind === kind)
  )
}

function shapeOf(config: LivingDocsConfig, file: string): ModuleShape {
  const absolute = resolvePath(config, file)
  const cached = shapes.get(absolute)
  if (cached) return cached

  const shape: ModuleShape = {
    declared: new Set(),
    local: new Map(),
    reexported: new Map(),
    stars: [],
    imports: new Map(),
  }
  const source = ts.createSourceFile(
    absolute,
    readFileSync(absolute, "utf8"),
    ts.ScriptTarget.Latest,
    false,
    /x$/.test(file) ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  )
  for (const statement of source.statements) {
    if (ts.isImportDeclaration(statement)) {
      const clause = statement.importClause
      if (!clause || clause.isTypeOnly) continue
      const specifier = (statement.moduleSpecifier as ts.StringLiteral).text
      if (clause.name) {
        shape.imports.set(clause.name.text, { specifier, imported: "default" })
      }
      const bindings = clause.namedBindings
      if (bindings && ts.isNamedImports(bindings)) {
        for (const element of bindings.elements) {
          shape.imports.set(element.name.text, {
            specifier,
            imported: (element.propertyName ?? element.name).text,
          })
        }
      }
    } else if (ts.isExportAssignment(statement)) {
      shape.declared.add("default")
      if (ts.isIdentifier(statement.expression)) {
        shape.defaultName = statement.expression.text
      }
    } else if (ts.isExportDeclaration(statement)) {
      if (statement.isTypeOnly) continue
      const specifier =
        statement.moduleSpecifier &&
        ts.isStringLiteral(statement.moduleSpecifier)
          ? statement.moduleSpecifier.text
          : undefined
      const clause = statement.exportClause
      if (!clause) {
        if (specifier) shape.stars.push(specifier)
      } else if (ts.isNamespaceExport(clause)) {
        shape.declared.add(clause.name.text)
      } else {
        for (const element of clause.elements) {
          if (element.isTypeOnly) continue
          const name = element.name.text
          const original = (element.propertyName ?? element.name).text
          if (specifier) {
            shape.reexported.set(name, { specifier, imported: original })
          } else {
            shape.local.set(name, original)
          }
        }
      }
    } else if (hasModifier(statement, ts.SyntaxKind.ExportKeyword)) {
      if (hasModifier(statement, ts.SyntaxKind.DefaultKeyword)) {
        shape.declared.add("default")
        if (
          (ts.isFunctionDeclaration(statement) ||
            ts.isClassDeclaration(statement)) &&
          statement.name
        ) {
          shape.defaultName = statement.name.text
        }
      } else if (ts.isVariableStatement(statement)) {
        for (const declaration of statement.declarationList.declarations) {
          if (ts.isIdentifier(declaration.name)) {
            shape.declared.add(declaration.name.text)
          }
        }
      } else if (
        (ts.isFunctionDeclaration(statement) ||
          ts.isClassDeclaration(statement) ||
          ts.isEnumDeclaration(statement)) &&
        statement.name
      ) {
        shape.declared.add(statement.name.text)
      }
    }
  }
  shapes.set(absolute, shape)
  return shape
}

export type ExportOrigin =
  | {
      kind: "file"
      file: string
      /** The export's name there; `default` for a default export. */
      name: string
      /** What to call it: its own name, even when exported as default. */
      displayName: string
    }
  | { kind: "package"; name: string; exportName: string }

/**
 * Where `file`'s export `name` is declared, following re-exports and barrel
 * files; undefined when the file does not export it.
 */
export function findExport(
  config: LivingDocsConfig,
  file: string,
  name: string,
  seen = new Set<string>()
): ExportOrigin | undefined {
  const visit = `${file}#${name}`
  if (seen.has(visit)) return
  seen.add(visit)

  const follow = (specifier: string, imported: string, star = false) => {
    const target = resolveModule(config, specifier, file)
    // A package's exports aren't read, so `export *` from one proves nothing.
    if (target.kind === "package" && !star) {
      return {
        kind: "package" as const,
        name: target.name,
        exportName: imported,
      }
    }
    return target.kind === "file"
      ? findExport(config, target.file, imported, seen)
      : undefined
  }

  const shape = shapeOf(config, file)
  const origin = { kind: "file" as const, file, name }
  if (shape.declared.has(name)) {
    const displayName = name === "default" ? shape.defaultName : name
    return { ...origin, displayName: displayName ?? name }
  }
  const local = shape.local.get(name)
  if (local !== undefined) {
    const imported = shape.imports.get(local)
    return imported
      ? follow(imported.specifier, imported.imported)
      : { ...origin, displayName: name }
  }
  const reexport = shape.reexported.get(name)
  if (reexport) return follow(reexport.specifier, reexport.imported)
  if (name === "default") return
  for (const specifier of shape.stars) {
    const found = follow(specifier, name, true)
    if (found) return found
  }
}
