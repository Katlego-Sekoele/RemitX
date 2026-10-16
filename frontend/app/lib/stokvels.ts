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
  type BeneficiaryRead,
  type StokvelPayoutOrderRequest,
  type SentStokvelInvitationRead,
  type StokvelContributionRead,
  type StokvelCycleStartRequest,
  type StokvelInvitationCreateRequest,
  type StokvelInvitationRead,
  type StokvelListRead,
  type StokvelRead,
} from "~/client"
import { amountToCents, fromCents } from "~/lib/money"
import type { StokvelRoundTimes } from "~/lib/stokvel-schedule"
import {
  demoStokvelsMock,
  acceptInvitationMock,
  contributeMock,
  declineInvitationMock,
  getStokvelContractStatusMock,
  getStokvelMock,
  inviteMock,
  setMyBeneficiaryMock,
  setPayoutOrderMock,
  startCycleMock,
} from "~/lib/stokvels.mock"

export type {
  SentStokvelInvitationRead,
  StokvelContributionRead,
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
  /** Has chosen a payout beneficiary for the next cycle. A cycle starts
   * only when every member has (#232). */
  payout_ready: boolean
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
  /** The pool in the Stokvel currency once released; null before. */
  pool_fiat_amount: string | null
  /** The payout remittance's reference once it exists. */
  remittance_reference: string | null
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
export type StokvelRoundContributionRead = {
  contribution_id: string
  cycle_id: string
  round: number
  member_id: string
  amount_fiat: string
  amount_token: string
  /** The member's fee share, paid on top (D6), as the API's `fee_amount`. */
  fee_amount: string
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
  contributions: StokvelRoundContributionRead[]
  /** True for a real stokvel built from its list row while
   * `GET /stokvels/{id}` (#236) isn't wired: its phase, members and
   * invitations aren't known, so nothing may act on them. R4-09: drop. */
  partial: boolean
  /** Member ids in the payout order the Organiser entered for the next
   * cycle (D3), or null until entered. Index = round. */
  planned_payout_order: string[] | null
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

/** The mock's invitation ids start `inv_`; the API's are UUIDs. */
export function isDemoInvitation(invitationId: string): boolean {
  return invitationId.startsWith("inv_")
}

/** Whether a call goes to the mock: a demo id, in development only. In
 * production a demo id goes to the API like any other and is not found. */
function usesMock(isDemo: boolean): boolean {
  return import.meta.env.DEV && isDemo
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
    partial: true,
    planned_payout_order: null,
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
        usesMock(isDemoStokvel(stokvelId))
          ? getStokvelMock(stokvelId)
          : detailFromList(stokvelId, signal),
    }),
  contract: () =>
    queryOptions({
      queryKey: ["admin", "stokvel-contract"],
      queryFn: () => getStokvelContractStatusMock(),
    }),
}

/** Mutations in the shape `useMutation` spreads, like the client's. */
export const stokvelMutations = {
  /** `POST /stokvels/{id}/contributions` (#233, built): pays the open round
   * and returns it `pending`. Demo stokvels pay the mock. */
  contribute: (stokvelId: string) => ({
    mutationFn: async (): Promise<StokvelContributionRead> => {
      if (usesMock(isDemoStokvel(stokvelId))) return contributeMock(stokvelId)
      const { data } = await sdk.stokvels.contributeToStokvel({
        path: { stokvel_id: stokvelId },
        throwOnError: true,
      })
      return data
    },
  }),
  /** `POST /stokvels/{id}/invitations` (#230, built): Organiser only. */
  invite: (stokvelId: string) => ({
    mutationFn: async (
      body: StokvelInvitationCreateRequest
    ): Promise<SentStokvelInvitationRead> => {
      if (usesMock(isDemoStokvel(stokvelId))) return inviteMock(stokvelId, body)
      const { data } = await sdk.stokvels.inviteToStokvel({
        path: { stokvel_id: stokvelId },
        body,
        throwOnError: true,
      })
      return data
    },
  }),
  /** `POST /invitations/{id}/accept` (#230, built): the invitee joins and
   * gets back the stokvel. */
  acceptInvitation: () => ({
    mutationFn: async (invitationId: string): Promise<StokvelRead> => {
      if (usesMock(isDemoInvitation(invitationId))) {
        return acceptInvitationMock(invitationId)
      }
      const { data } = await sdk.stokvels.acceptStokvelInvitation({
        path: { invitation_id: invitationId },
        throwOnError: true,
      })
      return data
    },
  }),
  /** `PUT /stokvels/{id}/members/me/beneficiary` (#231, built): the payout
   * goes to this beneficiary in their saved payout currency. */
  setMyBeneficiary: (stokvelId: string) => ({
    mutationFn: async (beneficiary: BeneficiaryRead): Promise<void> => {
      if (usesMock(isDemoStokvel(stokvelId))) {
        return setMyBeneficiaryMock(stokvelId, beneficiary)
      }
      await sdk.stokvels.setMyBeneficiary({
        path: { stokvel_id: stokvelId },
        body: { beneficiary_id: beneficiary.beneficiary_id },
        throwOnError: true,
      })
    },
  }),
  /** `PUT /stokvels/{id}/payout-order` (#231, built): Organiser only. */
  setPayoutOrder: (stokvelId: string) => ({
    mutationFn: async (body: StokvelPayoutOrderRequest): Promise<void> => {
      if (usesMock(isDemoStokvel(stokvelId))) {
        return setPayoutOrderMock(stokvelId, body)
      }
      await sdk.stokvels.setPayoutOrder({
        path: { stokvel_id: stokvelId },
        body,
        throwOnError: true,
      })
    },
  }),
  /** `POST /stokvels/{id}/cycles` (#232, built in #348): one round per
   * current member, in payout order. Pending invitations lapse. */
  startCycle: (stokvelId: string) => ({
    mutationFn: async (body: StokvelCycleStartRequest): Promise<void> => {
      if (usesMock(isDemoStokvel(stokvelId))) {
        return startCycleMock(stokvelId, body)
      }
      await sdk.stokvels.startStokvelCycle({
        path: { stokvel_id: stokvelId },
        body,
        throwOnError: true,
      })
    },
  }),
  /** `POST /invitations/{id}/decline` (#230, built). Revoking (#297) is not
   * built yet, so the Organiser has no Revoke button. */
  declineInvitation: () => ({
    mutationFn: async (invitationId: string): Promise<void> => {
      if (usesMock(isDemoInvitation(invitationId))) {
        return declineInvitationMock(invitationId)
      }
      await sdk.stokvels.declineStokvelInvitation({
        path: { invitation_id: invitationId },
        throwOnError: true,
      })
    },
  }),
}

/** Invitations still waiting for an answer. */
export function pendingInvitations(
  detail: Pick<StokvelDetailRead, "invitations">
): SentStokvelInvitationRead[] {
  return detail.invitations.filter(
    (invitation) => invitation.status === InvitationStatus.pending
  )
}

/**
 * Whether the Organiser can invite now: the stokvel is being set up and has
 * a free place. Pending invitations don't hold places (the cap is checked
 * when someone accepts, #230), so only current members count.
 */
export function canInvite(
  detail: Pick<
    StokvelDetailRead,
    | "phase"
    | "is_organiser"
    | "member_count"
    | "max_members"
    | "deactivated_at"
    | "partial"
  >
): boolean {
  return (
    !detail.partial &&
    detail.deactivated_at === null &&
    detail.phase === CycleStatus.forming &&
    detail.is_organiser &&
    detail.member_count < detail.max_members
  )
}

/** An account reference as the API stores it: trimmed and lower-case. The
 * invite route matches it exactly (`AccountRepository.
 * get_user_account_by_reference`), so `Thandi2-ZAR` must go as `thandi2-zar`,
 * as the beneficiary and deposit lookups already do. */
export function normaliseReference(reference: string): string {
  return reference.trim().toLowerCase()
}

/** Why the Organiser can't start the cycle yet, in the order to fix them
 * (#232's `too_few_members` and `cycle_not_ready`); empty when it can. */
export function startCycleBlockers(
  detail: Pick<StokvelDetailRead, "members" | "planned_payout_order" | "phase">
): string[] {
  if (detail.phase !== CycleStatus.forming) return []
  const blockers: string[] = []
  if (detail.members.length < 2) {
    blockers.push("A cycle needs at least 2 members.")
  }
  for (const member of detail.members) {
    if (!member.payout_ready) {
      blockers.push(
        member.is_me
          ? "Choose your payout beneficiary."
          : `${member.full_name.split(" ")[0]} hasn't chosen a payout beneficiary yet.`
      )
    }
  }
  const order = detail.planned_payout_order ?? []
  const everyone = new Set(detail.members.map((m) => m.member_id))
  if (
    order.length !== everyone.size ||
    !order.every((memberId) => everyone.has(memberId))
  ) {
    blockers.push("Set the payout order.")
  }
  return blockers
}

/** The planned order, completed with any member not in it yet (a new member
 * joins at the end), so the Organiser always has a full list. */
export function payoutOrderWithEveryone(
  detail: Pick<StokvelDetailRead, "members" | "planned_payout_order">
): string[] {
  const everyone = detail.members.map((m) => m.member_id)
  const kept = (detail.planned_payout_order ?? []).filter((id) =>
    everyone.includes(id)
  )
  return [...kept, ...everyone.filter((id) => !kept.includes(id))]
}

/** `order` with the item at `from` moved one place up (-1) or down (+1). */
export function moveInOrder(
  order: readonly string[],
  from: number,
  step: -1 | 1
): string[] {
  const to = from + step
  if (from < 0 || to < 0 || from >= order.length || to >= order.length) {
    return [...order]
  }
  const next = [...order]
  ;[next[from], next[to]] = [next[to], next[from]]
  return next
}

/** The development-only scenario knobs, re-exported so pages import every
 * stokvel thing from this file and R4-09 stays a change here. */
export {
  resetStokvelMockScenario,
  simulateInviteesAcceptMock,
  stokvelMockScenario,
} from "~/lib/stokvels.mock"

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

/** Explorer links come from `lib/chain`, which reads `VITE_EVM_EXPLORER_URL`
 * (#257), so every page links the same way. */
export {
  EVM_EXPLORER_URL,
  explorerAddressUrl,
  explorerTxUrl,
} from "~/lib/chain"

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

/** A contribution's hash as proof of payment: only once it is confirmed. The
 * worker stores the hash before sending, so a pending one may never be
 * mined (doc §3). */
export function contributionProofHash(
  contribution: Pick<StokvelRoundContributionRead, "status" | "evm_tx_hash">
): string | null {
  return contribution.status === ContributionStatus.confirmed
    ? contribution.evm_tx_hash
    : null
}

/**
 * A round's payout hash as proof. The burn hash is stored before the burn is
 * sent (#278), so it is proof only once the payout remittance is confirmed;
 * until then the release's hash is, once the release is confirmed.
 */
export function payoutProofHash(
  round: Pick<
    StokvelRoundRead,
    "release_status" | "remittance_status" | "burn_tx_hash" | "release_tx_hash"
  >
): string | null {
  if (
    round.remittance_status === RemittanceStatus.confirmed &&
    round.burn_tx_hash
  ) {
    return round.burn_tx_hash
  }
  return round.release_status === ReleaseStatus.released
    ? round.release_tx_hash
    : null
}

/**
 * The signed-in member's contribution to the current round, ignoring failed
 * attempts: after a failed send the member pays again, and the live attempt
 * is the one the panel follows.
 */
export function myCurrentContribution(
  detail: Pick<StokvelDetailRead, "cycle" | "contributions" | "my_member_id">
): StokvelRoundContributionRead | undefined {
  const cycle = detail.cycle
  if (!cycle) return undefined
  return detail.contributions.find(
    (c) =>
      c.cycle_id === cycle.cycle_id &&
      c.round === cycle.current_round &&
      c.member_id === detail.my_member_id &&
      c.status !== ContributionStatus.failed
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

/** Where a round's payout is, in the words members see (product docx §2):
 * collecting → released → sending → delivered, or failed. */
export type PayoutStage =
  "collecting" | "released" | "sending" | "delivered" | "failed"

export function payoutStage(
  round: Pick<StokvelRoundRead, "release_status" | "remittance_status">,
  everyonePaid: boolean
): PayoutStage {
  if (round.remittance_status === RemittanceStatus.confirmed) return "delivered"
  // A failed release never reaches a remittance, so check it first.
  if (round.release_status === ReleaseStatus.failed) return "failed"
  if (round.remittance_status === RemittanceStatus.failed) return "failed"
  if (round.remittance_status) return "sending"
  if (round.release_status === ReleaseStatus.released) return "released"
  if (round.release_status === ReleaseStatus.processing) return "released"
  return everyonePaid ? "released" : "collecting"
}

export const PAYOUT_STAGE_LABELS: Record<PayoutStage, string> = {
  collecting: "Waiting",
  released: "Released",
  sending: "Sending",
  delivered: "Delivered",
  failed: "Didn't go through",
}

/** Members who have not paid `round` of the current cycle. */
export function outstandingMembers(
  detail: Pick<StokvelDetailRead, "cycle" | "contributions" | "members">,
  round: number = detail.cycle?.current_round ?? 0
): StokvelMemberRead[] {
  const paid = paidMemberIds(detail, round)
  return detail.members.filter((member) => !paid.has(member.member_id))
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
