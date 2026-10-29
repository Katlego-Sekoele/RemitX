import { ArrowSquareOutIcon } from "@phosphor-icons/react"

import { CopyButton } from "~/components/accounts/copy-button"
import { Button } from "~/components/ui/button"
import {
  CHAIN_LABELS,
  chainOfHash,
  explorerTxUrl,
  shortHash,
} from "~/lib/chain"

/**
 * A transaction hash on either chain (R4-08, #257): shortened, linked to the
 * right testnet explorer for its format, with a copy button for the whole
 * hash. Replaces the XRPL-only `TxHash` and `XrplHash`.
 */
export function ChainTxHash({ hash }: { hash: string }) {
  const chain = CHAIN_LABELS[chainOfHash(hash)]
  return (
    <span className="inline-flex items-center gap-1">
      <Button
        variant="link"
        size="xs"
        nativeButton={false}
        render={
          <a
            href={explorerTxUrl(hash)}
            target="_blank"
            rel="noreferrer"
            title={hash}
          />
        }
      >
        <code className="font-mono">{shortHash(hash)}</code>
        <ArrowSquareOutIcon data-icon="inline-end" aria-hidden="true" />
        <span className="sr-only">View on the {chain} explorer</span>
      </Button>
      <CopyButton value={hash} label="Transaction hash" />
    </span>
  )
}
