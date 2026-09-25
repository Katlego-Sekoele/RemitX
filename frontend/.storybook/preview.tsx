import {
  Controls,
  Description,
  Primary,
  Stories,
  Subtitle,
  Title,
} from "@storybook/addon-docs/blocks"
import type { Decorator, Preview } from "@storybook/react-vite"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useLayoutEffect, useState, type ReactNode } from "react"
import { MemoryRouter } from "react-router"

import { ProductContext } from "../living-docs/blocks/product-context.tsx"

import "../app/app.css"

function Theme({ theme, children }: { theme: string; children: ReactNode }) {
  useLayoutEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
  }, [theme])
  return children
}

function Providers({ children }: { children: ReactNode }) {
  // One client per story, so no story sees another's cached data.
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } })
  )
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const withApp: Decorator = (Story, context) => (
  <Theme theme={context.globals.theme}>
    <Providers>
      <MemoryRouter initialEntries={context.parameters.router?.initialEntries}>
        <Story />
      </MemoryRouter>
    </Providers>
  </Theme>
)

const preview: Preview = {
  tags: ["autodocs"],
  decorators: [withApp],
  globalTypes: {
    theme: {
      description: "Light or dark theme",
      toolbar: {
        title: "Theme",
        icon: "mirror",
        items: [
          { value: "light", title: "Light", icon: "sun" },
          { value: "dark", title: "Dark", icon: "moon" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "light" },
  parameters: {
    layout: "centered",
    options: {
      storySort: {
        order: [
          "Overview",
          "Journeys",
          "Concepts",
          "Components",
          "APIs",
          "Database",
        ],
      },
    },
    docs: {
      // Storybook's default page, plus where the component is used in the
      // product (living-docs/blocks/product-context.tsx).
      page: () => (
        <>
          <Title />
          <Subtitle />
          <Description />
          <Primary />
          <Controls />
          <Stories />
          <ProductContext />
        </>
      ),
    },
  },
}

export default preview
