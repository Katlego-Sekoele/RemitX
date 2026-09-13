import type { ComponentProps } from "react"
import { cn } from "cn"

/** Label/value pairs read at a glance. Owns their type styles so feature
 * components only choose which pairs to show. */
function DescriptionList({ className, ...props }: ComponentProps<"dl">) {
  return (
    <dl
      data-slot="description-list"
      className={cn("grid gap-x-6 gap-y-4 sm:grid-cols-2", className)}
      {...props}
    />
  )
}

function DescriptionItem({
  className,
  wide = false,
  ...props
}: ComponentProps<"div"> & { wide?: boolean }) {
  return (
    <div
      data-slot="description-item"
      data-wide={wide || undefined}
      className={cn(
        "flex min-w-0 flex-col gap-1 data-wide:sm:col-span-2",
        className
      )}
      {...props}
    />
  )
}

function DescriptionTerm({ className, ...props }: ComponentProps<"dt">) {
  return (
    <dt
      data-slot="description-term"
      className={cn("text-xs text-muted-foreground", className)}
      {...props}
    />
  )
}

function DescriptionDetails({ className, ...props }: ComponentProps<"dd">) {
  return (
    <dd
      data-slot="description-details"
      className={cn(
        "text-sm font-medium break-words text-foreground",
        className
      )}
      {...props}
    />
  )
}

export { DescriptionDetails, DescriptionItem, DescriptionList, DescriptionTerm }
