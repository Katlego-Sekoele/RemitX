import { defineConfig } from "@hey-api/openapi-ts"

import { defineNamespacesPlugin } from "./openapi-ts/namespaces"

// Generates app/client from openapi.json, which the API exports
// (cd api && python scripts/export_openapi.py). The output is gitignored and
// rebuilt by `predev`, `prebuild` and `typecheck`, so every environment —
// local, Docker, CI, Render — generates from the committed spec.
export default defineConfig({
  input: "./openapi.json",
  output: {
    path: "./app/client",
    // The generated tree is not ours to format; prettier ignores it too.
    postProcess: [],
  },
  plugins: [
    {
      name: "@hey-api/client-fetch",
      // Base URL and the Clerk token, set before the first request.
      runtimeConfigPath: "./app/lib/api-client-config",
    },
    "@hey-api/typescript",
    // Flat functions stay out of the entry file: app code reaches operations
    // through the `api` and `sdk` namespaces instead.
    { name: "@hey-api/sdk", includeInEntry: false },
    { name: "@tanstack/react-query", includeInEntry: false },
    defineNamespacesPlugin(),
  ],
})
