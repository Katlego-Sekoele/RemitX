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
import { useLayoutEffect, useRef, useState, type ReactNode } from "react"
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

/**
 * On a docs page a story mounts beside others, after the page is laid out.
 * A field that focuses itself on mount (add-beneficiary-form) would scroll
 * the page to it and take the keyboard from the reader: both are undone
 * before the browser paints.
 */
function StayPut({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null)
  const [top] = useState(() => window.scrollY)
  useLayoutEffect(() => {
    const focused = document.activeElement
    if (focused instanceof HTMLElement && root.current?.contains(focused)) {
      focused.blur()
      window.scrollTo({ top })
    }
  }, [top])
  return (
    <div ref={root} style={{ display: "contents" }}>
      {children}
    </div>
  )
}

const withApp: Decorator = (Story, context) => {
  const story = (
    <Theme theme={context.globals.theme}>
      <Providers>
        <MemoryRouter
          initialEntries={context.parameters.router?.initialEntries}
        >
          <Story />
        </MemoryRouter>
      </Providers>
    </Theme>
  )
  return context.viewMode === "docs" ? <StayPut>{story}</StayPut> : story
}

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
      // product (living-docs/blocks/product-context.tsx). Stories leaves out
      // the primary story shown above it: a second copy repeats its element
      // ids, and an autofocused field (add-beneficiary-form) takes focus in
      // that copy, below the fold.
      page: () => (
        <>
          <Title />
          <Subtitle />
          <Description />
          <Primary />
          <Controls />
          <Stories includePrimary={false} />
          <ProductContext />
        </>
      ),
    },
  },
}

export default preview
