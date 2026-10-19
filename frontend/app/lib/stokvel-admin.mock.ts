/** Mocked admin stokvel rounds and manual release (R4-11, #260) until
 * R3-10 (#247). Deleted by R4-09 (#258). One round per demo state: ready,
 * waiting for a member, before its payout time, and already released. */

import type { AdminStokvelRoundRead } from "~/lib/stokvel-admin"

const DAY = 24 * 60 * 60 * 1000

function initialRounds(now = Date.now()): AdminStokvelRoundRead[] {
  return [
    {
      stokvel_id: "stk_8c21",
      stokvel_name: "December groceries",
      round: 1,
      total_rounds: 3,
      recipient_name: "Sipho Khumalo",
      paid_count: 3,
      member_count: 3,
      // Fully paid and past its payout time: the automatic release stalled.
      payout_time: new Date(now - DAY).toISOString(),
      release_status: "pending",
      release_tx_hash: null,
    },
    {
      stokvel_id: "stk_4d10",
      stokvel_name: "Burial society",
      round: 0,
      total_rounds: 3,
      recipient_name: "Thandi Nkosi",
      paid_count: 2,
      member_count: 3,
      payout_time: new Date(now - 2 * DAY).toISOString(),
      release_status: "pending",
      release_tx_hash: null,
    },
    {
      stokvel_id: "stk_9a33",
      stokvel_name: "Taxi fund",
      round: 0,
      total_rounds: 2,
      recipient_name: "Naledi Mokoena",
      paid_count: 2,
      member_count: 2,
      payout_time: new Date(now + 3 * DAY).toISOString(),
      release_status: "pending",
      release_tx_hash: null,
    },
    {
      stokvel_id: "stk_02bd",
      stokvel_name: "School fees 2026",
      round: 2,
      total_rounds: 3,
      recipient_name: "Lerato Nkosi",
      paid_count: 3,
      member_count: 3,
      payout_time: new Date(now - 30 * DAY).toISOString(),
      release_status: "released",
      release_tx_hash: `0x${"5e".repeat(32)}`,
    },
  ]
}

let rounds = initialRounds()

/** Shaped like `ApiError` (lib/api.ts), with the doc §6 `{ detail, code }`. */
function apiError(message: string, status: number, code?: string): Error {
  return Object.assign(new Error(message), {
    name: "ApiError",
    status,
    body: code ? { code, detail: message } : { detail: message },
  })
}

function settle<T>(value: T, delayMs = 300): Promise<T> {
  return new Promise((resolve) =>
    setTimeout(() => resolve(structuredClone(value)), delayMs)
  )
}

export function listAdminRoundsMock(): Promise<AdminStokvelRoundRead[]> {
  return settle(rounds, 200)
}

/** The contract's rule (D12): release only a fully paid round whose payout
 * time has passed; `NotYetFinalisable` and `AlreadyFinalised` otherwise. */
export async function finaliseRoundMock(
  stokvelId: string,
  round: number
): Promise<AdminStokvelRoundRead> {
  await settle(null, 600)
  const row = rounds.find(
    (r) => r.stokvel_id === stokvelId && r.round === round
  )
  if (!row) throw apiError("Stokvel not found.", 404)
  if (row.release_status === "released") {
    throw apiError(
      "This round has already been paid out.",
      409,
      "round_already_finalised"
    )
  }
  if (
    row.paid_count < row.member_count ||
    Date.parse(row.payout_time) > Date.now()
  ) {
    throw apiError(
      "This round can't be paid out yet.",
      409,
      "round_not_finalisable"
    )
  }
  row.release_status = "released"
  // A made-up but valid 32-byte hash: the id's characters as hex.
  row.release_tx_hash = `0x${[...row.stokvel_id]
    .map((char) => char.charCodeAt(0).toString(16))
    .join("")
    .padEnd(64, "f")
    .slice(0, 64)}`
  return structuredClone(row)
}

/** For tests: back to the demo states. */
export function resetAdminRoundsMock() {
  rounds = initialRounds()
}
