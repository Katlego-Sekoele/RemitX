import { ArrowSquareOutIcon } from "@phosphor-icons/react"

import { CopyButton } from "~/components/accounts/copy-button"
import { Button } from "~/components/ui/button"

const EXPLORER = "https://testnet.xrpl.org/transactions"

/** "A1B2…9F0E" */
export function truncateHash(hash: string) {
  return hash.length > 10 ? `${hash.slice(0, 4)}…${hash.slice(-4)}` : hash
}

/** An XRPL Testnet transaction hash: truncated, linked to the testnet
 * explorer, with a copy button for the whole thing. */
export function TxHash({ hash }: { hash: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Button
        variant="link"
        size="xs"
        nativeButton={false}
        render={
          <a
            href={`${EXPLORER}/${hash}`}
            target="_blank"
            rel="noreferrer"
            title={hash}
          />
        }
      >
        <code className="font-mono">{truncateHash(hash)}</code>
        <ArrowSquareOutIcon data-icon="inline-end" aria-hidden="true" />
        <span className="sr-only">View on the XRPL Testnet explorer</span>
      </Button>
      <CopyButton value={hash} label="XRPL hash" />
    </span>
  )
}
