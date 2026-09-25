import type { ReactNode } from "react"
import { NAVIGATE_URL } from "storybook/internal/core-events"
import { addons } from "storybook/preview-api"

import { cn } from "~/lib/utils"

export type LinkTarget =
  { story: string } | { docs: string } | { anchor: string }

/**
 * A link to another Storybook page. A plain click navigates the manager over
 * the channel, as Storybook's own docs links do, so the page swaps without a
 * reload; the href still opens the page in a new tab.
 */
export function DocLink({
  to,
  className,
  title,
  children,
}: {
  to: LinkTarget
  className?: string
  title?: string
  children: ReactNode
}) {
  const classes = cn(
    "inline-flex items-center gap-1 underline-offset-4 hover:underline",
    className
  )
  if ("anchor" in to) {
    return (
      <a href={`#${to.anchor}`} className={classes} title={title}>
        {children}
      </a>
    )
  }
  const path = "story" in to ? `/story/${to.story}` : `/docs/${to.docs}`
  return (
    <a
      // index.html by name: a static host need not serve a directory index.
      // _parent is Storybook's manager, even when the admin app embeds it.
      href={`./index.html?path=${path}`}
      target="_parent"
      className={classes}
      title={title}
      onClick={(event) => {
        const modified =
          event.metaKey || event.ctrlKey || event.shiftKey || event.altKey
        if (event.button !== 0 || modified) return
        event.preventDefault()
        addons.getChannel().emit(NAVIGATE_URL, `?path=${path}`)
      }}
    >
      {children}
    </a>
  )
}
