import { CopyButton } from "~/components/accounts/copy-button"

/** An account reference in monospace, with a copy button beside it. */
export function AccountReference({ reference }: { reference: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <code className="font-mono">{reference}</code>
      <CopyButton value={reference} label="Reference" />
    </span>
  )
}
