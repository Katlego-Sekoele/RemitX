/**
 * The living docs from the command line. Node >= 22.18 runs this TypeScript
 * as is; `npm run docs:check` and friends wrap it.
 *
 *   node living-docs/cli.ts check [--strict] [--format text|markdown]
 *       Resolve every reference the docs make; exit 1 on an error (or, with
 *       --strict, a warning).
 *   node living-docs/cli.ts impact --base <git-ref> [--format text|markdown]
 *       What the API and schema changes since <git-ref> touch in the docs.
 *   node living-docs/cli.ts graph
 *       Print the product graph as JSON.
 *   node living-docs/cli.ts canonicalize-dbml <file>
 *       Print a db2dbml file with its unordered parts sorted
 *       (scripts/generate-dbml.sh runs this).
 */
import { execFileSync } from "node:child_process"
import { readFileSync } from "node:fs"
import { parseArgs } from "node:util"

type Command = (args: string[]) => Promise<number>

const commands: Record<string, Command> = {
  async check(args) {
    const { values } = parseArgs({
      args,
      options: {
        strict: { type: "boolean", default: false },
        format: { type: "string", default: "text" },
      },
    })
    if (values.format !== "text" && values.format !== "markdown") {
      throw new Error("--format is text or markdown")
    }
    const { buildGraph } = await import("./load/graph.ts")
    const { checkReport, counts } = await import("./report.ts")
    const { graph } = buildGraph()
    process.stdout.write(checkReport(graph, values.format))
    const { errors, warnings } = counts(graph)
    return errors > 0 || (values.strict && warnings > 0) ? 1 : 0
  },

  async impact(args) {
    const { values } = parseArgs({
      args,
      options: {
        base: { type: "string" },
        format: { type: "string", default: "text" },
      },
    })
    const { base, format } = values
    if (!base) throw new Error("--base <git-ref> is required")
    if (format !== "text" && format !== "markdown") {
      throw new Error("--format is text or markdown")
    }
    const { config } = await import("./config.ts")
    const git = (...gitArgs: string[]) =>
      execFileSync("git", gitArgs, {
        cwd: config.root,
        encoding: "utf8",
        maxBuffer: 64 * 1024 * 1024,
        stdio: ["ignore", "pipe", "ignore"],
      })
    try {
      git("rev-parse", "--verify", "--quiet", `${base}^{commit}`)
    } catch {
      throw new Error(`${base} is not a commit here; fetch it first`)
    }
    // A source the base did not have yet counts as empty.
    const atBase = (file: string) => {
      try {
        return git("show", `${base}:${file}`)
      } catch {
        return undefined
      }
    }

    const { ingestOpenApi } = await import("./load/openapi.ts")
    const { emptyDatabase, ingestDbml } = await import("./load/dbml.ts")
    const { buildGraph } = await import("./load/graph.ts")
    const { diffApi, diffDatabase, impactReport } = await import("./impact.ts")

    const spec = atBase(config.sources.openapi)
    const dbml = atBase(config.sources.dbml)
    const before = {
      api: ingestOpenApi(spec ? JSON.parse(spec) : {}, config.sources.openapi)
        .api,
      database: dbml
        ? ingestDbml(dbml, config.sources.dbml, config.ignoredTables).database
        : emptyDatabase(config.sources.dbml),
    }
    const { graph } = buildGraph(config)
    const changes = {
      api: diffApi(before.api, graph.api),
      database: diffDatabase(before.database, graph.database),
    }
    process.stdout.write(impactReport(graph, changes, base, format))
    return 0
  },

  async graph() {
    const { buildGraph } = await import("./load/graph.ts")
    process.stdout.write(JSON.stringify(buildGraph().graph, null, 2) + "\n")
    return 0
  },

  async "canonicalize-dbml"([file]) {
    if (!file) throw new Error("usage: canonicalize-dbml <file>")
    const { canonicalizeDbml } = await import("./load/dbml.ts")
    process.stdout.write(canonicalizeDbml(readFileSync(file, "utf8")))
    return 0
  },
}

const [name = "", ...args] = process.argv.slice(2)
const command = commands[name]
if (!command) {
  console.error(
    `usage: node living-docs/cli.ts <${Object.keys(commands).join("|")}>`
  )
  process.exit(2)
}
try {
  process.exit(await command(args))
} catch (error) {
  console.error(`living-docs ${name}: ${(error as Error).message}`)
  process.exit(2)
}
