import { ArrowSquareOutIcon } from "@phosphor-icons/react"
import { useRef, type MouseEvent } from "react"
import { useSearchParams } from "react-router"

import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { Button } from "~/components/ui/button"
import { Card } from "~/components/ui/card"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/docs"

// The literal path, not `import.meta.filename` — see routes/admin/access.tsx.
const ROUTE_MODULE = "routes/admin/docs.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

/**
 * The living product docs are a Storybook build that `npm run build:site`
 * publishes beside the app, at /storybook/. `npm run dev` has no such build,
 * so locally this shows `npm run storybook` instead.
 */
const DOCS_URL = import.meta.env.DEV
  ? "http://localhost:6006/"
  : "/storybook/index.html"

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * Storybook in the admin shell. `?path=` is Storybook's own page address
 * (`/docs/journeys-send-money--docs`), so a link can open a given page.
 */
export default function AdminDocs() {
  const [params] = useSearchParams()
  const path = params.get("path")
  // Storybook's addons panel is for developing components; readers get the
  // page at full height, and the toolbar can still bring the panel back.
  const query = new URLSearchParams({ panel: "false" })
  if (path?.startsWith("/")) query.set("path", path)
  const src = `${DOCS_URL}?${query}`
  const frame = useRef<HTMLIFrameElement>(null)

  // Opens whatever page the frame is on now. Its location is readable when
  // it is same-origin, as in production; otherwise the link keeps `src`.
  const openCurrent = (event: MouseEvent<HTMLAnchorElement>) => {
    try {
      const current = frame.current?.contentWindow?.location.href
      if (current && current !== "about:blank") {
        event.currentTarget.href = current
      }
    } catch {
      // Cross-origin in dev: the start page will do.
    }
  }

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-1 flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <PageHeader>
            <PageHeaderTitle>{pageRoutingContext?.title}</PageHeaderTitle>
            <PageHeaderDescription>
              How RemitX works end to end: user journeys, the screens they use,
              the API operations those call and the tables behind them.
            </PageHeaderDescription>
          </PageHeader>
          <Button
            variant="outline"
            nativeButton={false}
            render={
              <a
                href={src}
                target="_blank"
                rel="noreferrer"
                onClick={openCurrent}
              />
            }
          >
            <ArrowSquareOutIcon data-icon="inline-start" aria-hidden="true" />
            Open in new tab
          </Button>
        </div>
        <Card className="flex-1 gap-0 overflow-hidden py-0">
          <iframe
            ref={frame}
            src={src}
            title="Product docs"
            className="min-h-[75svh] w-full flex-1"
          />
        </Card>
      </div>
    </AdminPageFrame>
  )
}
