import type { ComponentProps } from "react"
import { cn } from "cn"

/** A page's title and the sentence under it. Owns their type styles so pages
 * only lay themselves out. */
function PageHeader({ className, ...props }: ComponentProps<"header">) {
  return (
    <header
      data-slot="page-header"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function PageHeaderTitle({ className, ...props }: ComponentProps<"h1">) {
  return (
    <h1
      data-slot="page-header-title"
      className={cn(
        "font-heading text-2xl font-semibold tracking-tight",
        className
      )}
      {...props}
    />
  )
}

function PageHeaderDescription({ className, ...props }: ComponentProps<"p">) {
  return (
    <p
      data-slot="page-header-description"
      className={cn("max-w-xl text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export { PageHeader, PageHeaderDescription, PageHeaderTitle }
