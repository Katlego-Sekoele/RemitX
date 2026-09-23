import { fileURLToPath } from "node:url"
import { defineConfig } from "vitest/config"

// Kept apart from vite.config.ts so the React Router plugin, which expects
// to own the build, stays out of unit tests. Tests cover the logic in
// app/lib; pages are exercised by the manual test plan. The `~` alias is
// spelled out because tsconfig.json excludes test files, so its paths don't
// reach them.
export default defineConfig({
  resolve: {
    alias: { "~": fileURLToPath(new URL("./app", import.meta.url)) },
  },
  test: {
    include: ["app/**/*.test.ts"],
  },
})
