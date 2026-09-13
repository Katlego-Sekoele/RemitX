import {
  $,
  definePluginConfig,
  type DefinePlugin,
  type IR,
  type Plugin,
} from "@hey-api/openapi-ts"
import type ts from "typescript"

/**
 * Hey API plugin: groups the generated operations into namespaces taken from
 * their OpenAPI tag, split on `separator`.
 *
 * An operation tagged `admin.users` with id `grantUserRole` becomes
 *
 *   api.admin.users.grantUserRole()  → TanStack mutation options
 *   sdk.admin.users.grantUserRole()  → the raw request
 *
 * It generates nothing of its own: every leaf is a reference to a symbol the
 * `@tanstack/react-query` or `@hey-api/sdk` plugin already emitted, looked up by
 * the operation id and the role that plugin registered it under. So whether an
 * operation is a query or a mutation is whatever TanStack decided, and a
 * rename of `{{name}}Options` upstream cannot break the tree.
 */

type UserConfig = Plugin.Name<"api"> &
  Plugin.Hooks &
  Plugin.UserExports & {
    /** Splits a tag into namespace segments. @default "." */
    separator?: string
  }

type Config = Plugin.Name<"api"> &
  Plugin.Hooks &
  Plugin.Exports & {
    separator: string
  }

type NamespacesPlugin = DefinePlugin<UserConfig, Config>

declare module "@hey-api/shared" {
  interface PluginConfigMap {
    api: NamespacesPlugin["Types"]
  }
}

type Node = {
  children: Map<string, Node>
  operations: Map<string, IR.OperationObject>
}

const newNode = (): Node => ({ children: new Map(), operations: new Map() })

const IDENTIFIER = /^[A-Za-z_$][\w$]*$/

const handler: NamespacesPlugin["Handler"] = ({ plugin }) => {
  const root = newNode()

  plugin.forEach("operation", ({ operation }) => {
    const tags = operation.tags ?? []
    if (tags.length !== 1) {
      throw new Error(
        `Operation "${operation.id}" has ${tags.length} tags; exactly one ` +
          "is needed to place it in a namespace."
      )
    }

    let node = root
    for (const segment of tags[0].split(plugin.config.separator)) {
      // Unquoted keys keep `api.admin.users` dot-accessible.
      if (!IDENTIFIER.test(segment)) {
        throw new Error(
          `Tag "${tags[0]}" on "${operation.id}": "${segment}" is not an ` +
            "identifier."
        )
      }
      if (node.operations.has(segment)) {
        throw new Error(
          `Namespace "${tags[0]}" collides with operation "${segment}".`
        )
      }
      if (!node.children.has(segment)) node.children.set(segment, newNode())
      node = node.children.get(segment)!
    }
    if (node.children.has(operation.id)) {
      throw new Error(
        `Operation "${operation.id}" collides with a namespace of that name.`
      )
    }
    node.operations.set(operation.id, operation)
  })

  const reference = (query: Record<string, unknown>) =>
    $.lazy<ts.Expression>((ctx) => ctx.access(plugin.referenceSymbol(query)))

  const hookFor = (operation: IR.OperationObject) => {
    for (const role of ["queryOptions", "mutationOptions"]) {
      const query = {
        category: "hook",
        resource: "operation",
        resourceId: operation.id,
        role,
      }
      if (plugin.isSymbolRegistered(query)) return reference(query)
    }
    // Not generated for this operation (e.g. server-sent events): the SDK
    // tree still carries it.
    return undefined
  }

  const sdkFor = (operation: IR.OperationObject) =>
    reference({
      category: "sdk",
      resource: "operation",
      resourceId: operation.id,
    })

  const build = (
    node: Node,
    leaf: (
      operation: IR.OperationObject
    ) => ReturnType<typeof reference> | undefined
  ) => {
    const object = $.object().pretty()
    for (const [name, child] of node.children) {
      object.prop(name, build(child, leaf))
    }
    for (const [name, operation] of node.operations) {
      const value = leaf(operation)
      if (value) object.prop(name, value)
    }
    return object
  }

  plugin.node(
    $.const(plugin.symbol("api"))
      .export()
      .doc([
        "TanStack Query options, namespaced by OpenAPI tag. Queries take the",
        "request options; mutations take theirs through `mutate`.",
        "",
        "@example useQuery(api.admin.roles.listRoles())",
        "@example useMutation(api.admin.users.grantUserRole())",
      ])
      .assign(build(root, hookFor))
  )

  plugin.node(
    $.const(plugin.symbol("sdk"))
      .export()
      .doc([
        "The raw requests, namespaced like `api`. For calls outside TanStack",
        "Query, such as a mutation that makes two requests.",
        "",
        "@example await sdk.kyc.onboarding.getApplication({ throwOnError: true })",
      ])
      .assign(build(root, sdkFor))
  )
}

export const defaultConfig: NamespacesPlugin["Config"] = {
  config: { includeInEntry: true, separator: "." },
  dependencies: ["@hey-api/sdk", "@tanstack/react-query"],
  handler,
  name: "api",
}

export const defineNamespacesPlugin = definePluginConfig(defaultConfig)
