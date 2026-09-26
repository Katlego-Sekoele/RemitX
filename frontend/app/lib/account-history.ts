import type { AccountRead, AccountTransactionRead } from "~/client"
import { sumMoney } from "~/lib/money"

/** One line of an account's history. Usually one ledger leg; on a fiat
 * account, a transfer's fee and net legs fold into one line. */
export type HistoryRow = {
  key: string
  legs: AccountTransactionRead[]
  description: string
  direction: string
  /** Everything the line moved, fees included, as a 2 dp string. */
  amount: string
  /** The fee part of `amount`, when the line folds a fee leg in. */
  fees: string | null
  currency: string
  status: AccountTransactionRead["status"]
  created_at: string
  remittance_id: string | null
  xrpl_tx_hash: string | null
}

export const HISTORY_PAGE_SIZE = 50

/**
 * Lines in the order the API sent their legs (newest first). A transfer
 * lands on the sender's fiat account as a "Transfer fee" leg and a
 * "Sent to …" leg; those become one line, placed where the first of them
 * appears. The RLUSD wallet keeps every leg: its in and out legs are the
 * transfer's incoming and cash-out rows, each worth seeing.
 */
export function historyRows(
  legs: readonly AccountTransactionRead[],
  kind: AccountRead["kind"]
): HistoryRow[] {
  const rows: HistoryRow[] = []
  const grouped = new Map<string, AccountTransactionRead[]>()

  for (const leg of legs) {
    const group = kind === "fiat" ? leg.remittance_id : null
    if (group) {
      const existing = grouped.get(group)
      if (existing) {
        existing.push(leg)
        continue
      }
      grouped.set(group, [leg])
    }
    rows.push(single(leg))
  }

  return rows.map((row) => {
    const legsInGroup = row.remittance_id
      ? grouped.get(row.remittance_id)
      : null
    return legsInGroup && legsInGroup.length > 1 ? folded(legsInGroup) : row
  })
}

function single(leg: AccountTransactionRead): HistoryRow {
  return {
    key: leg.tx_id,
    legs: [leg],
    description: leg.description,
    direction: leg.direction,
    amount: leg.amount,
    fees: null,
    currency: leg.currency,
    status: leg.status,
    created_at: leg.created_at,
    remittance_id: leg.remittance_id,
    xrpl_tx_hash: leg.xrpl_tx_hash,
  }
}

function folded(legs: AccountTransactionRead[]): HistoryRow {
  const feeLegs = legs.filter((leg) => leg.type === "fee")
  const main = legs.find((leg) => leg.type !== "fee") ?? legs[0]
  return {
    ...single(main),
    key: `transfer-${main.remittance_id}`,
    legs,
    amount: sumMoney(legs.map((leg) => leg.amount)),
    fees: feeLegs.length ? sumMoney(feeLegs.map((leg) => leg.amount)) : null,
    // The newest of the group, so the line sorts where the transfer did.
    created_at: legs[0].created_at,
  }
}
