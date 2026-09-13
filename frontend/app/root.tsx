import { QueryClientProvider } from "@tanstack/react-query"
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  isRouteErrorResponse,
} from "react-router"

import { AppShell } from "~/components/app-shell"
import { ChromeBar, HomeLink } from "~/components/app-chrome"
import { ThemeProvider } from "~/components/theme-provider"
import { ThemeToggle } from "~/components/theme-toggle"
import { queryClient } from "~/lib/query-client"
import {
  SITE_DESCRIPTION,
  SITE_NAME,
  SITE_SOCIAL_DESCRIPTION,
  SITE_TITLE,
  SITE_URL,
  SOCIAL_IMAGE_URL,
  THEME_COLOR,
} from "~/lib/site"
import { PageLoader } from "~/components/remitx-loader"
import { Toaster } from "~/components/ui/sonner"
import type { Route } from "./+types/root"
import "./app.css"

const themeInitScript = `(function(){try{var storedTheme=localStorage.getItem("theme");var prefersDark=window.matchMedia("(prefers-color-scheme: dark)").matches;var theme=storedTheme||"system";if(theme==="dark"||(theme==="system"&&prefersDark)){document.documentElement.classList.add("dark")}}catch(_error){}})()`

export const links: Route.LinksFunction = () => [
  {
    rel: "icon",
    href: "/favicon-light.svg",
    type: "image/svg+xml",
    media: "(prefers-color-scheme: light)",
  },
  {
    rel: "icon",
    href: "/favicon-dark.svg",
    type: "image/svg+xml",
    media: "(prefers-color-scheme: dark)",
  },
  { rel: "icon", href: "/favicon.svg", type: "image/svg+xml" },
  {
    rel: "icon",
    href: "/favicon-32.png",
    sizes: "32x32",
    type: "image/png",
  },
  { rel: "icon", href: "/favicon.ico", sizes: "any" },
  {
    rel: "apple-touch-icon",
    href: "/apple-touch-icon.png",
    sizes: "180x180",
  },
  { rel: "manifest", href: "/site.webmanifest" },
]

export function meta(): Route.MetaDescriptors {
  return [
    { title: SITE_TITLE },
    { name: "description", content: SITE_DESCRIPTION },
    { name: "application-name", content: SITE_NAME },
    { name: "theme-color", content: THEME_COLOR },
    { name: "color-scheme", content: "light dark" },
    { name: "robots", content: "index, follow" },
    { property: "og:site_name", content: SITE_NAME },
    { property: "og:type", content: "website" },
    { property: "og:locale", content: "en_ZA" },
    { property: "og:url", content: SITE_URL },
    { property: "og:title", content: SITE_TITLE },
    { property: "og:description", content: SITE_SOCIAL_DESCRIPTION },
    { property: "og:image", content: SOCIAL_IMAGE_URL },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { property: "og:image:alt", content: `${SITE_NAME} logo` },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:title", content: SITE_TITLE },
    { name: "twitter:description", content: SITE_SOCIAL_DESCRIPTION },
    { name: "twitter:image", content: SOCIAL_IMAGE_URL },
    { name: "twitter:image:alt", content: `${SITE_NAME} logo` },
  ]
}

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <Meta />
        <Links />
      </head>
      <body>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            {children}
            <Toaster />
          </ThemeProvider>
        </QueryClientProvider>
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  )
}

/** Shown while route modules load and before the app hydrates. */
export function HydrateFallback() {
  return <PageLoader label="Loading RemitX" />
}

export default function App() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  let message = "Oops!"
  let details = "An unexpected error occurred."
  let stack: string | undefined

  if (isRouteErrorResponse(error)) {
    message = error.status === 404 ? "404" : "Error"
    details =
      error.status === 404
        ? "The requested page could not be found."
        : error.statusText || details
  } else if (import.meta.env.DEV && error && error instanceof Error) {
    details = error.message
    stack = error.stack
  }

  return (
    <>
      <HomeLink />
      <ChromeBar>
        <ThemeToggle />
      </ChromeBar>
      <main className="container mx-auto p-4 pt-16">
        <h1>{message}</h1>
        <p>{details}</p>
        {stack && (
          <pre className="w-full overflow-x-auto p-4">
            <code>{stack}</code>
          </pre>
        )}
      </main>
    </>
  )
}
