import { ArrowSquareOutIcon, CopyIcon } from "@phosphor-icons/react"
import { toast } from "sonner"

import { Button } from "~/components/ui/button"
import { explorerUrl, shortHash } from "~/lib/transfers"

/** An XRPL transaction hash: truncated, copyable, and linked to the Testnet
 * explorer. */
export function XrplHash({ hash }: { hash: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Button
        variant="link"
        size="sm"
        nativeButton={false}
        render={<a href={explorerUrl(hash)} target="_blank" rel="noreferrer" />}
        title={hash}
      >
        {shortHash(hash)}
        <ArrowSquareOutIcon data-icon="inline-end" aria-hidden="true" />
        <span className="sr-only">(opens the XRPL Testnet explorer)</span>
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Copy the transaction hash"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(hash)
            toast.success("Hash copied")
          } catch {
            // Clipboard refused (permissions, insecure context): the full
            // hash is still in the link's title and the explorer.
          }
        }}
      >
        <CopyIcon />
      </Button>
    </span>
  )
}
