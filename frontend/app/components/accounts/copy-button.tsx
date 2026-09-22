import { CheckIcon, CopyIcon } from "@phosphor-icons/react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "~/components/ui/button"

const COPIED_DISPLAY_MS = 1500

type CopyButtonProps = {
  value: string
  /** What's being copied, for the screen-reader label and the toast. */
  label: string
}

/** Copies `value` to the clipboard, with a toast to say it worked. */
export function CopyButton({ value, label }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), COPIED_DISPLAY_MS)
    return () => clearTimeout(timer)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      toast.success(`${label} copied`)
    } catch {
      // Clipboard access can be refused (permissions, insecure origin). The
      // value is on screen beside the button, so it can still be selected.
      setCopied(false)
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      onClick={copy}
      aria-label={`Copy ${label.toLowerCase()}`}
    >
      {copied ? <CheckIcon /> : <CopyIcon />}
    </Button>
  )
}
