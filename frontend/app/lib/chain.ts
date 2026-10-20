/**
 * Which chain a transaction hash is on, and where to look it up (R4-08,
 * #257). Settlement is moving from the XRPL to the XRPL EVM Testnet (D1),
 * and the XRPL path is kept so we can switch back (D11), so the explorer is
 * chosen from the hash itself: EVM hashes are `0x` + 64 hex digits, XRPL
 * hashes are 64 hex digits without a prefix. Old XRPL links keep working.
 */

/** `EVM_EXPLORER_URL` in .env.example; the frontend reads the `VITE_` copy. */
export const EVM_EXPLORER_URL = (
  import.meta.env.VITE_EVM_EXPLORER_URL ||
  "https://explorer.testnet.xrplevm.org"
).replace(/\/+$/, "")

export const XRPL_EXPLORER_URL = "https://testnet.xrpl.org"

export type Chain = "evm" | "xrpl"

export const CHAIN_LABELS: Record<Chain, string> = {
  evm: "XRPL EVM Testnet",
  xrpl: "XRPL Testnet",
}

export function chainOfHash(hash: string): Chain {
  return /^0x/i.test(hash.trim()) ? "evm" : "xrpl"
}

/** The explorer page for a transaction on whichever chain it is on. */
export function explorerTxUrl(hash: string): string {
  const trimmed = hash.trim()
  return chainOfHash(trimmed) === "evm"
    ? `${EVM_EXPLORER_URL}/tx/${trimmed}`
    : `${XRPL_EXPLORER_URL}/transactions/${trimmed}`
}

/** The explorer page for an EVM address (the stokvel contract, wallets). */
export function explorerAddressUrl(address: string): string {
  return `${EVM_EXPLORER_URL}/address/${address.trim()}`
}

/** `A1B2…9F0E`, or `0x51a0…9b0e` for an EVM hash (the prefix is kept so the
 * two read differently). */
export function shortHash(hash: string): string {
  const prefix = chainOfHash(hash) === "evm" ? hash.slice(0, 2) : ""
  const body = hash.slice(prefix.length)
  return body.length <= 10
    ? hash
    : `${prefix}${body.slice(0, 4)}…${body.slice(-4)}`
}
