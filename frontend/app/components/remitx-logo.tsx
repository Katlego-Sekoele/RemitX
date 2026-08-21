import { cn } from "~/lib/utils"

type RemitXLogoProps = {
  className?: string
}

/**
 * Brand mark with light/dark variants.
 *
 * The navy path (#01213B) disappears on dark backgrounds, so dark mode
 * swaps in a light slate stroke. Both images stay in the DOM; visibility
 * follows the `dark` class from next-themes (no hydration mismatch).
 */
export function RemitXLogo({ className }: RemitXLogoProps) {
  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      <img
        src="/remitx-logo-light.svg"
        alt=""
        className="size-full dark:hidden"
      />
      <img
        src="/remitx-logo-dark.svg"
        alt=""
        className="hidden size-full dark:block"
      />
    </span>
  )
}
