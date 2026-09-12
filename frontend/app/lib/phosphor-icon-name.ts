import type { Icon } from "@phosphor-icons/react"
import type * as PhosphorIcons from "@phosphor-icons/react"

/** Export name of a Phosphor icon component, e.g. `"IdentificationCardIcon"`. */
export type PhosphorIconName = {
  [K in keyof typeof PhosphorIcons]: (typeof PhosphorIcons)[K] extends Icon
    ? K
    : never
}[keyof typeof PhosphorIcons]
