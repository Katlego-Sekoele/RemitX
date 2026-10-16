/** Stokvel screen data and helpers (R4-02, #251).
 *
 * The stokvel routes do not exist in `frontend/openapi.json` yet (#229, #230,
 * #236), so the queries here read `stokvels.mock.ts`. R4-09 (#258) swaps each
 * query for `api.stokvels.<operation>()` and deletes the mock. Shapes follow
 * docs/stokvel_integration.md §3 (tables, status values) and §5 (routes), so
 * the swap should be a change to this file only.
 */

import { queryOptions, type QueryClient } from "@tanstack/react-query"

import { amountToCents, fromCents } from "~/lib/money"
import {
  createStokvelMock,
  getStokvelContractStatusMock,
  getStokvelMock,
  listStokvelsMock,
} from "~/lib/stokvels.mock"

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

export type StokvelMemberRead = {
  member_id: string
  user_id: string
  full_name: string
  is_organiser: boolean
  is_me: boolean
  joined_at: string
}

export type StokvelInvitationRead = {
  invitation_id: string
  stokvel_id: string
  stokvel_name: string
  organiser_name: string
  currency: string
  /** Fiat estimate of the contribution at today's rate, 2 dp. */
  contribution_fiat_estimate: string
  member_count: number
  status: InvitationStatus
  created_at: string
}

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

/** One row of `GET /stokvels`. */
export type StokvelSummaryRead = {
  stokvel_id: string
  name: string
  goal: string | null
  /** Stokvel currency (fiat), e.g. "ZAR". */
  currency: string
  /** Fixed UCTUSD amount per contribution (D13), as a decimal string. */
  contribution_amount: string
  /** Fiat estimate of `contribution_amount` at today's rate, 2 dp. */
  contribution_fiat_estimate: string
  organiser_name: string
  is_organiser: boolean
  member_count: number
  /** Derived from the current cycle; `forming` when none has started. */
  phase: CycleStatus
  current_round: number | null
  total_rounds: number | null
  next_payout_time: string | null
  my_contribution_status: ContributionStatus | null
}

/** `GET /stokvels`: the caller's stokvels and pending invitations. */
export type StokvelListRead = {
  stokvels: StokvelSummaryRead[]
  invitations: StokvelInvitationRead[]
}

export type StokvelBeneficiaryChoice = {
  beneficiary_id: string
  full_name: string
  payout_currency: string
}

/** One round of the schedule the Organiser sets (doc §12 step 1), before a
 * cycle exists. ISO datetimes. */
export type StokvelScheduleRound = {
  round: number
  start_time: string
  deadline: string
  payout_time: string
}

/** `GET /stokvels/{id}`: everything the member screen shows (R2-14, #236). */
export type StokvelDetailRead = StokvelSummaryRead & {
  my_member_id: string
  my_beneficiary: StokvelBeneficiaryChoice | null
  members: StokvelMemberRead[]
  invitations: StokvelInvitationRead[]
  cycle: StokvelCycleRead | null
  contributions: StokvelContributionRead[]
  /** The planned rounds while no cycle has started; null once it has. */
  schedule: StokvelScheduleRound[] | null
}

/**
 * `POST /stokvels` (R2-07, #229). Shape assumed by the frontend, recorded in
 * doc §5: the Organiser enters the contribution in the Stokvel currency and
 * the API fixes the UCTUSD amount at the live rate (D13).
 */
export type StokvelCreateRequest = {
  name: string
  goal: string | null
  currency: string
  contribution_fiat_amount: string
  rounds: StokvelScheduleRound[]
}

/** Admin view of the contract (R3-07, #244). */
export type StokvelContractStatusRead = {
  address: string
  network: string
  paused: boolean
  treasury_token_balance: string
}

/** Query options in the shape the generated client will give us, so pages
 * spread them into `useQuery` exactly as they will after R4-09. */
export const stokvelQueries = {
  list: () =>
    queryOptions({
      queryKey: ["stokvels", "list"],
      queryFn: () => listStokvelsMock(),
    }),
  detail: (stokvelId: string) =>
    queryOptions({
      queryKey: ["stokvels", "detail", stokvelId],
      queryFn: () => getStokvelMock(stokvelId),
    }),
  contract: () =>
    queryOptions({
      queryKey: ["admin", "stokvel-contract"],
      queryFn: () => getStokvelContractStatusMock(),
    }),
}

/** Mutations in the shape `useMutation` spreads, like the client's. */
export const stokvelMutations = {
  create: () => ({
    mutationFn: (body: StokvelCreateRequest) => createStokvelMock(body),
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
