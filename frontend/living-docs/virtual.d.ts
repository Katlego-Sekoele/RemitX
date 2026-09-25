// Modules the living-docs Vite plugin (storybook/vite-plugin.ts) serves.

declare module "virtual:living-docs/graph" {
  const graph: import("./model.ts").ProductGraph
  export default graph
}

declare module "virtual:living-docs/components" {
  /** The graph key of a component a docs page imports, by identity. */
  export function componentKey(
    component: unknown
  ): import("./model.ts").NodeKey | undefined
}
