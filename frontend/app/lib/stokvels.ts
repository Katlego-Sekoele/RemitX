/** Stokvel screen data and helpers (R4-02, #251).
 *
 * Built routes use the generated client and its types (`~/client`):
 * `GET` and `POST /stokvels` (R2-07, #229). `GET /stokvels/{id}` (#236) is
 * not built yet, so the detail read and its types below are the frontend's
 * assumption from docs/stokvel_integration.md §3 and §5, each marked
 * `R4-09`, and read `stokvels.mock.ts`. R4-09 (#258) replaces them and
 * deletes the mock. In development the list also shows the mock's demo
 * stokvels, so every screen state can be opened.
 */

import { queryOptions, type QueryClient } from "@tanstack/react-query"

import {
  sdk,
  type SentStokvelInvitationRead,
  type StokvelInvitationRead,
  type StokvelListRead,
  type StokvelRead,
} from "~/client"
import { amountToCents, fromCents } from "~/lib/money"
import {
  demoStokvelsMock,
  getStokvelContractStatusMock,
  getStokvelMock,
} from "~/lib/stokvels.mock"

export type {
  SentStokvelInvitationRead,
  StokvelCreateRequest,
  StokvelInvitationRead,
  StokvelListRead,
  StokvelRead,
} from "~/client"

// Status values from docs/stokvel_integration.md §3 "Status values and
// transitions". Objects, not enums, so they can be iterated like the
// generated client's enums (`Object.values(...)`).

export const InvitationStatus = {
  pending: "pending",
  accepted: "accepted",
  declined: "declined",
  revoked: "revoked",
  lapsed: "lapsed",
} as const
export type InvitationStatus =
  (typeof InvitationStatus)[keyof typeof InvitationStatus]

export const CycleStatus = {
  forming: "forming",
  active: "active",
  closed: "closed",
} as const
export type CycleStatus = (typeof CycleStatus)[keyof typeof CycleStatus]

export const ContributionStatus = {
  pending: "pending",
  processing: "processing",
  confirmed: "confirmed",
  failed: "failed",
} as const
export type ContributionStatus =
  (typeof ContributionStatus)[keyof typeof ContributionStatus]

export const ReleaseStatus = {
  pending: "pending",
  processing: "processing",
  released: "released",
  failed: "failed",
} as const
export type ReleaseStatus = (typeof ReleaseStatus)[keyof typeof ReleaseStatus]

/** The ledger's names, kept over the brief's (doc §3, D4 in the ticket plan). */
export const RemittanceStatus = {
  pending: "pending",
  processing: "processing",
  confirmed: "confirmed",
  failed: "failed",
} as const
export type RemittanceStatus =
  (typeof RemittanceStatus)[keyof typeof RemittanceStatus]

/** R4-09: assumed until #236 (or #244 for the contract). */
export type StokvelMemberRead = {
  member_id: string
  user_id: string
  full_name: string
  is_organiser: boolean
  is_me: boolean
  joined_at: string
}

/** R4-09: assumed until #236 (or #244 for the contract). */
export type StokvelRoundRead = {
  /** 0-based, like the contract and `stokvel_cycles.current_round`. */
  round: number
  start_time: string
  deadline: string
  payout_time: string
  recipient_member_id: string
  release_status: ReleaseStatus | null
  remittance_status: RemittanceStatus | null
  remittance_id: string | null
  release_tx_hash: string | null
  burn_tx_hash: string | null
}

/** R4-09: assumed until #236 (or #244 for the contract). */
export type StokvelCycleRead = {
  cycle_id: string
  cycle_number: number
  status: CycleStatus
  current_round: number
  total_rounds: number
  started_at: string | null
  closed_at: string | null
  /** Member ids in payout order; index = round. */
  payout_order: string[]
  rounds: StokvelRoundRead[]
}

/** R4-09: assumed until #236 (or #244 for the contract). */
export type StokvelContributionRead = {
  contribution_id: string
  cycle_id: string
  round: number
  member_id: string
  amount_fiat: string
  amount_token: string
  status: ContributionStatus
  evm_tx_hash: string | null
  created_at: string
}

/** R4-09: assumed until #236 (or #244 for the contract). */
export type StokvelBeneficiaryChoice = {
  beneficiary_id: string
  full_name: string
  payout_currency: string
}

/** `GET /stokvels/{id}`: everything the member screen shows (#236).
 * R4-09: replace with `~/client` once #236 is built; everything past
 * `StokvelRead` is assumed. */
export type StokvelDetailRead = StokvelRead & {
  organiser_name: string
  /** Fiat estimate of `contribution_amount` at today's rate, 2 dp. */
  contribution_fiat_estimate: string
  /** Derived from the current cycle; `forming` when none has started. */
  phase: CycleStatus
  current_round: number | null
  total_rounds: number | null
  next_payout_time: string | null
  my_contribution_status: ContributionStatus | null
  my_member_id: string
  my_beneficiary: StokvelBeneficiaryChoice | null
  members: StokvelMemberRead[]
  invitations: SentStokvelInvitationRead[]
  cycle: StokvelCycleRead | null
  contributions: StokvelContributionRead[]
}

/** Admin view of the contract (R3-07, #244). */
/** R4-09: assumed until #236 (or #244 for the contract). */
export type StokvelContractStatusRead = {
  address: string
  network: string
  paused: boolean
  treasury_token_balance: string
}

/** Mock ids start `stk_`; the API's are UUIDs. */
export function isDemoStokvel(stokvelId: string): boolean {
  return stokvelId.startsWith("stk_")
}

/**
 * A stokvel the API has but `GET /stokvels/{id}` can't return yet (#236):
 * its list row as a forming stokvel, priced at today's rate. R4-09: delete.
 */
async function detailFromList(
  stokvelId: string,
  signal: AbortSignal
): Promise<StokvelDetailRead> {
  const { data } = await sdk.stokvels.listStokvels({
    signal,
    throwOnError: true,
  })
  const row = data.stokvels.find((s) => s.stokvel_id === stokvelId)
  if (!row) throw new Error("Stokvel not found")
  const { data: preview } = await sdk.quotes.previewQuote({
    body: {
      sender_amount: "1000.00",
      sender_currency: row.currency,
      receiver_payout_currency: row.currency,
    },
    signal,
    throwOnError: true,
  })
  return {
    ...row,
    organiser_name: row.is_organiser ? "you" : "the organiser",
    contribution_fiat_estimate: tokenToFiat(
      row.contribution_amount,
      preview.fiat_to_token_exchange_rate
    ),
    phase: CycleStatus.forming,
    current_round: null,
    total_rounds: null,
    next_payout_time: null,
    my_contribution_status: null,
    my_member_id: "",
    my_beneficiary: null,
    members: [],
    invitations: [],
    cycle: null,
    contributions: [],
  }
}

export const stokvelQueries = {
  /** `GET /stokvels`, plus the mock's demo stokvels in development. */
  list: () =>
    queryOptions({
      queryKey: ["stokvels", "list"],
      queryFn: async ({ signal }): Promise<StokvelListRead> => {
        const { data } = await sdk.stokvels.listStokvels({
          signal,
          throwOnError: true,
        })
        if (!import.meta.env.DEV) return data
        const demo = await demoStokvelsMock()
        return {
          stokvels: [...data.stokvels, ...demo.stokvels],
          invitations: [...data.invitations, ...demo.invitations],
        }
      },
    }),
  /** R4-09: `GET /stokvels/{id}` once #236 is built. */
  detail: (stokvelId: string) =>
    queryOptions({
      queryKey: ["stokvels", "detail", stokvelId],
      // Demo data only in development, like the list: in production a
      // `stk_` id is looked up like any other and is not found.
      queryFn: ({ signal }) =>
        import.meta.env.DEV && isDemoStokvel(stokvelId)
          ? getStokvelMock(stokvelId)
          : detailFromList(stokvelId, signal),
    }),
  contract: () =>
    queryOptions({
      queryKey: ["admin", "stokvel-contract"],
      queryFn: () => getStokvelContractStatusMock(),
    }),
}

export async function invalidateStokvels(queryClient: QueryClient) {
  await queryClient.invalidateQueries({ queryKey: ["stokvels"] })
}

export function stokvelsPath(): string {
  return "/app/stokvels"
}

export function stokvelNewPath(): string {
  return "/app/stokvels/new"
}

export function stokvelPath(stokvelId: string): string {
  return `/app/stokvels/${stokvelId}`
}

/** Explorer for the XRPL EVM Testnet. R4-08 (#257) moves this into the
 * tx-hash component with the API's `EVM_EXPLORER_URL`. */
export const EVM_EXPLORER_URL = "https://explorer.testnet.xrplevm.org"

export function explorerTxUrl(hash: string): string {
  return `${EVM_EXPLORER_URL}/tx/${hash}`
}

export function explorerAddressUrl(address: string): string {
  return `${EVM_EXPLORER_URL}/address/${address}`
}

/** "Round 2 of 3" from a 0-based round index. */
export function roundLabel(round: number, totalRounds: number): string {
  return `Round ${round + 1} of ${totalRounds}`
}

/** The pool for one round: every member pays the same amount. */
export function poolAmount(amount: string, memberCount: number): string {
  return fromCents(amountToCents(amount) * BigInt(memberCount))
}

/**
 * Each member's share of a round's payout fee, paid on top of their
 * contribution (D6, #340): the fee and margin on the whole pool, split
 * evenly and rounded up to the cent, as the API's `contribution_fee_share`
 * does. An estimate until the member pays; the API fixes the real one then.
 */
export function feeShare(
  fee: string,
  margin: string,
  memberCount: number
): string {
  if (memberCount <= 0) throw new Error("A round needs members")
  // Ledger decimals can carry 8 places: add them exactly, then round the
  // share up to the cent.
  const a = parseDecimal(fee)
  const b = parseDecimal(margin)
  const scale = Math.max(a.scale, b.scale)
  const total =
    a.digits * 10n ** BigInt(scale - a.scale) +
    b.digits * 10n ** BigInt(scale - b.scale)
  const divisor = BigInt(memberCount) * 10n ** BigInt(scale)
  const cents = (total * 100n + divisor - 1n) / divisor
  return fromCents(cents)
}

/** Decimal places of the ledger's token amounts (Numeric(20,8)). */
export const TOKEN_DP = 8

/** A stokvel's contribution is set in whole cents of UCTUSD. */
export const CONTRIBUTION_TOKEN_DP = 2

/** "27.4" → { digits: 274n, scale: 1 }. Non-negative plain decimals only. */
function parseDecimal(value: string): { digits: bigint; scale: number } {
  const match = /^(\d+)(?:\.(\d*))?$/.exec(value.trim())
  if (!match) throw new Error(`Not a non-negative decimal: ${value}`)
  const [, whole, fraction = ""] = match
  return { digits: BigInt(whole + fraction), scale: fraction.length }
}

/** `numerator / denominator` to `dp` places, rounded half up, no floats. */
function divideToPlaces(
  numerator: bigint,
  denominator: bigint,
  dp: number
): string {
  if (denominator === 0n) throw new Error("Division by zero")
  const scaled = numerator * 10n ** BigInt(dp)
  const quotient = (2n * scaled + denominator) / (2n * denominator)
  const digits = quotient.toString().padStart(dp + 1, "0")
  return dp === 0 ? digits : `${digits.slice(0, -dp)}.${digits.slice(-dp)}`
}

/**
 * The token amount a fiat amount buys, to `dp` places, rounded half up.
 * `rate` is the quote preview's `fiat_to_token_exchange_rate`: token units
 * per 1 unit of fiat. The create wizard sends it as `contribution_amount`
 * (D13).
 */
export function fiatToToken(
  fiat: string,
  rate: string,
  dp: number = TOKEN_DP
): string {
  const amount = parseDecimal(fiat)
  const perUnit = parseDecimal(rate)
  return divideToPlaces(
    amount.digits * perUnit.digits,
    10n ** BigInt(amount.scale + perUnit.scale),
    dp
  )
}

/** What a token amount costs in fiat at `rate`, to the cent: the rand
 * figure members see ("R500.00 at today's rate"). The token is never named
 * on screen. */
export function tokenToFiat(token: string, rate: string): string {
  const amount = parseDecimal(token)
  const perUnit = parseDecimal(rate)
  if (perUnit.digits === 0n) throw new Error("Cannot convert at a zero rate")
  return divideToPlaces(
    amount.digits * 10n ** BigInt(perUnit.scale),
    perUnit.digits * 10n ** BigInt(amount.scale),
    2
  )
}

/** Members whose contribution to `round` of the current cycle is confirmed. */
export function paidMemberIds(
  detail: Pick<StokvelDetailRead, "cycle" | "contributions">,
  round: number = detail.cycle?.current_round ?? 0
): Set<string> {
  const cycleId = detail.cycle?.cycle_id
  const paid = new Set<string>()
  if (!cycleId) return paid
  for (const contribution of detail.contributions) {
    if (
      contribution.cycle_id === cycleId &&
      contribution.round === round &&
      contribution.status === ContributionStatus.confirmed
    ) {
      paid.add(contribution.member_id)
    }
  }
  return paid
}

/** The member the current round pays out to, if a cycle is running. */
export function currentRecipientId(
  cycle: StokvelCycleRead | null
): string | null {
  if (!cycle || cycle.status !== CycleStatus.active) return null
  return cycle.payout_order[cycle.current_round] ?? null
}

export const PHASE_LABELS: Record<CycleStatus, string> = {
  forming: "Setting up",
  active: "Active",
  closed: "Cycle complete",
}

export const CONTRIBUTION_STATUS_LABELS: Record<ContributionStatus, string> = {
  pending: "Waiting",
  processing: "Confirming",
  confirmed: "Paid",
  failed: "Didn't go through",
}

export const INVITATION_STATUS_LABELS: Record<InvitationStatus, string> = {
  pending: "Pending",
  accepted: "Accepted",
  declined: "Declined",
  revoked: "Revoked",
  lapsed: "Lapsed",
}
