import * as React from "react"
import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cn } from "cn"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { Button } from "~/components/ui/button"

/**
 * Label/value rows in the shape of Clerk's `<UserProfile>` pages, for the
 * custom pages mounted inside it. Owns the type scale and spacing Clerk uses
 * (17px page title, 13px rows, a fixed label column) so those pages sit beside
 * Clerk's own without a visible seam, and feature code only lays out content.
 */
function SettingsPage({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="settings-page"
      className={cn("flex flex-col", className)}
      {...props}
    />
  )
}

function SettingsTitle({ className, ...props }: React.ComponentProps<"h2">) {
  return (
    <h2
      data-slot="settings-title"
      className={cn(
        "pb-5 text-[17px] leading-6 font-semibold text-foreground",
        className
      )}
      {...props}
    />
  )
}

function SettingsSection({
  className,
  ...props
}: React.ComponentProps<"section">) {
  return (
    <section
      data-slot="settings-section"
      className={cn(
        "flex flex-col gap-2 border-t py-4 sm:flex-row sm:gap-6",
        className
      )}
      {...props}
    />
  )
}

function SettingsSectionLabel({
  className,
  ...props
}: React.ComponentProps<"h3">) {
  return (
    <h3
      data-slot="settings-section-label"
      className={cn(
        "shrink-0 text-[13px] leading-[18px] font-medium text-foreground sm:w-48 sm:py-[7px]",
        className
      )}
      {...props}
    />
  )
}

// Clerk's section height eases when a value opens into its edit card and back.
const HEIGHT_TRANSITION = { duration: 0.2, ease: [0.4, 0, 0.2, 1] } as const

/** A section's values. Its height animates as they change, so opening and
 * closing an edit card slides rather than jumps. */
function SettingsSectionContent({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const inner = React.useRef<HTMLDivElement>(null)
  const [height, setHeight] = React.useState<number | "auto">("auto")
  const reduceMotion = useReducedMotion()

  React.useLayoutEffect(() => {
    const element = inner.current
    if (!element) return
    const observer = new ResizeObserver(() => setHeight(element.offsetHeight))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    // -m-1/p-1: room inside the clip for focus rings and the card's shadow.
    // `clip`, not `hidden`: focusing the input mid-animation must not scroll
    // the box and push the card's title out of view.
    <motion.div
      className="-m-1 min-w-0 flex-1 overflow-clip"
      initial={false}
      animate={{ height }}
      transition={reduceMotion ? { duration: 0 } : HEIGHT_TRANSITION}
    >
      <div
        ref={inner}
        data-slot="settings-section-content"
        className={cn("flex flex-col gap-2 p-1", className)}
        {...props}
      />
    </motion.div>
  )
}

/**
 * Cross-fades a section between its values and its edit card. The outgoing
 * content fades out before the incoming fades in, while
 * SettingsSectionContent eases the height between them — so closing animates
 * the same way opening does. Change `swapKey` to swap.
 */
function SettingsSwap({
  swapKey,
  children,
}: {
  swapKey: string
  children: React.ReactNode
}) {
  const reduceMotion = useReducedMotion()

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={swapKey}
        className="flex flex-col gap-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.12 }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}

/** One value in a section. Pass `render={<Link />}` to make the row a link. */
function SettingsItem({
  className,
  render,
  ...props
}: useRender.ComponentProps<"div">) {
  return useRender({
    defaultTagName: "div",
    props: mergeProps<"div">(
      {
        className: cn(
          "flex min-h-8 items-center gap-2 rounded-md py-1 pr-1 pl-2.5 text-[13px] text-foreground outline-none focus-visible:ring-1 focus-visible:ring-ring [a]:transition-colors [a]:hover:bg-muted",
          className
        ),
      },
      props
    ),
    render,
    state: { slot: "settings-item" },
  })
}

function SettingsItemDescription({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="settings-item-description"
      className={cn("min-w-0 text-muted-foreground", className)}
      {...props}
    />
  )
}

/** Clerk's section action: "Update profile", "+ Add email address". */
function SettingsAction({
  className,
  ...props
}: React.ComponentProps<typeof Button>) {
  return (
    <Button
      data-slot="settings-action"
      variant="ghost"
      className={cn(
        "self-start text-[13px] text-primary hover:text-primary",
        className
      )}
      {...props}
    />
  )
}

/** The panel a section's value turns into while it is edited. */
function SettingsEditCard({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="settings-edit-card"
      className={cn(
        "flex flex-col gap-4 rounded-lg bg-card px-5 py-4 text-[13px] shadow-sm ring-1 ring-foreground/5",
        className
      )}
      {...props}
    />
  )
}

function SettingsEditCardTitle({
  className,
  ...props
}: React.ComponentProps<"h4">) {
  return (
    <h4
      data-slot="settings-edit-card-title"
      className={cn("text-[13px] font-semibold text-foreground", className)}
      {...props}
    />
  )
}

function SettingsEditCardFooter({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="settings-edit-card-footer"
      className={cn("flex items-center justify-end gap-2", className)}
      {...props}
    />
  )
}

export {
  SettingsAction,
  SettingsEditCard,
  SettingsEditCardFooter,
  SettingsEditCardTitle,
  SettingsItem,
  SettingsItemDescription,
  SettingsPage,
  SettingsSection,
  SettingsSectionContent,
  SettingsSectionLabel,
  SettingsSwap,
  SettingsTitle,
}
