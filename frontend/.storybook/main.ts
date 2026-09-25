import { fileURLToPath } from "node:url"
import type { StorybookConfig } from "@storybook/react-vite"

import { config, sourceEntry, storiesEntry } from "../living-docs/config.ts"

// Storybook is the living product docs: components, plus the journeys under
// docs/, plus pages generated from the API spec and the database schema.
// frontend/living-docs/README.md explains how the pieces fit.
const storybook: StorybookConfig = {
  framework: "@storybook/react-vite",
  stories: [
    ...config.docSections.map((section) => storiesEntry(config, section)),
    storiesEntry(config, config.componentSection),
    // Read by the living-docs indexers: one page per operation and table.
    sourceEntry(config, config.sources.openapi),
    sourceEntry(config, config.sources.dbml),
  ],
  addons: [
    "@storybook/addon-docs",
    fileURLToPath(
      new URL("../living-docs/storybook/preset.ts", import.meta.url)
    ),
  ],
  core: { disableTelemetry: true },
  viteFinal(viteConfig) {
    // vite.config.ts is shared with the app, and the React Router plugin
    // expects to own the build: it has no place in Storybook's.
    viteConfig.plugins = (viteConfig.plugins ?? [])
      .flat()
      .filter(
        (plugin) =>
          !(
            plugin &&
            typeof plugin === "object" &&
            "name" in plugin &&
            plugin.name.startsWith("react-router")
          )
      )
    return viteConfig
  },
}

export default storybook
