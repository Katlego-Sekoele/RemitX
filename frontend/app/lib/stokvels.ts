/** Stokvel screen data and helpers (R4-02, #251; wired in R4-09, #258).
 *
 * Member screens use the generated client (`~/client`) and its types.
 * `GET /stokvels/{id}` is `stokvelQueries.detail`. Admin stokvel pages use
 * `~/lib/stokvel-contract` and `~/lib/stokvel-admin`.
 */

import { queryOptions, type QueryClient } from "@tanstack/react-query"

import {
  sdk,
  type BeneficiaryRead,
  type StokvelPayoutOrderRequest,
  type SentStokvelInvitationRead,
  type StokvelContinuationRead,
  type StokvelContinuationRequest,
  type StokvelContributionRead,
  type StokvelCycleStartRequest,
  type StokvelDetailCycleRead,
  type StokvelDetailRead,
  type StokvelRead,
  type StokvelInvitationCreateRequest,
  type StokvelMemberRead,
  type StokvelRoundContributionRead,
  type StokvelRoundRead,
} from "~/client"
import { amountToCents, fromCents } from "~/lib/money"

export type {
  SentStokvelInvitationRead,
  StokvelBeneficiaryChoiceRead,
  StokvelContributionRead,
  StokvelCreateRequest,
  StokvelDetailCycleRead,
  StokvelDetailInvitationRead,
  StokvelDetailRead,
  StokvelInvitationRead,
  StokvelListRead,
  StokvelMemberRead,
  StokvelRead,
  StokvelRoundContributionRead,
  StokvelRoundRead,
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

/** How often a stokvel screen asks again while it is open. */
export const STOKVEL_POLL_INTERVAL_MS = 3_000

/**
 * A contribution confirms on chain a few seconds after it is sent, so the
 * member's own pending or processing row is asked about sooner.
 */
export const STOKVEL_INFLIGHT_POLL_INTERVAL_MS = 1_500

/** Keep the last successful read. Stop only when there is nothing to show. */
export function stokvelPollInterval(query: {
  state: { data?: unknown }
}): number | false {
  return query.state.data == null ? false : STOKVEL_POLL_INTERVAL_MS
}

/** Same as `stokvelPollInterval`, faster while the caller's own pay is in
 * flight or the cycle is open in the database but not yet on the chain. */
export function stokvelDetailPollInterval(query: {
  state: {
    data?: {
      my_member_id: string
      contributions: { member_id: string; status: string }[]
      cycle?: { status: string; registered_at: string | null } | null
    }
  }
}): number | false {
  const data = query.state.data
  if (data == null) return false
  const inflight = data.contributions.some(
    (contribution) =>
      contribution.member_id === data.my_member_id &&
      (contribution.status === ContributionStatus.pending ||
        contribution.status === ContributionStatus.processing)
  )
  const opening =
    data.cycle?.status === CycleStatus.active &&
    data.cycle.registered_at == null
  return inflight || opening
    ? STOKVEL_INFLIGHT_POLL_INTERVAL_MS
    : STOKVEL_POLL_INTERVAL_MS
}

export const stokvelQueries = {
  /** `GET /stokvels`. */
  list: () =>
    queryOptions({
      queryKey: ["stokvels", "list"],
      queryFn: async ({ signal }) => {
        const { data } = await sdk.stokvels.listStokvels({
          signal,
          throwOnError: true,
        })
        return data
      },
      refetchInterval: stokvelPollInterval,
    }),
  /** `GET /stokvels/{id}` (#236). */
  detail: (stokvelId: string) =>
    queryOptions({
      queryKey: ["stokvels", "detail", stokvelId],
      queryFn: async ({ signal }) => {
        const { data } = await sdk.stokvels.getStokvel({
          path: { stokvel_id: stokvelId },
          signal,
          throwOnError: true,
        })
        return data
      },
      refetchInterval: stokvelDetailPollInterval,
    }),
}

/** Mutations in the shape `useMutation` spreads, like the client's. */
export const stokvelMutations = {
  /** `POST /stokvels/{id}/contributions` (#233): pays the open round. */
  contribute: (stokvelId: string) => ({
    mutationFn: async (): Promise<StokvelContributionRead> => {
      const { data } = await sdk.stokvels.contributeToStokvel({
        path: { stokvel_id: stokvelId },
        throwOnError: true,
      })
      return data
    },
  }),
  /** `POST /stokvels/{id}/invitations` (#230): Organiser only. */
  invite: (stokvelId: string) => ({
    mutationFn: async (
      body: StokvelInvitationCreateRequest
    ): Promise<SentStokvelInvitationRead> => {
      const { data } = await sdk.stokvels.inviteToStokvel({
        path: { stokvel_id: stokvelId },
        body,
        throwOnError: true,
      })
      return data
    },
  }),
  /** `POST /invitations/{id}/accept` (#230): the invitee joins and
   * gets back the stokvel. */
  acceptInvitation: () => ({
    mutationFn: async (invitationId: string): Promise<StokvelRead> => {
      const { data } = await sdk.stokvels.acceptStokvelInvitation({
        path: { invitation_id: invitationId },
        throwOnError: true,
      })
      return data
    },
  }),
  /** `PUT /stokvels/{id}/members/me/beneficiary` (#231): the payout
   * goes to this beneficiary in their saved payout currency. */
  setMyBeneficiary: (stokvelId: string) => ({
    mutationFn: async (beneficiary: BeneficiaryRead): Promise<void> => {
      await sdk.stokvels.setMyBeneficiary({
        path: { stokvel_id: stokvelId },
        body: { beneficiary_id: beneficiary.beneficiary_id },
        throwOnError: true,
      })
    },
  }),
  /** `PUT /stokvels/{id}/payout-order` (#231): Organiser only. */
  setPayoutOrder: (stokvelId: string) => ({
    mutationFn: async (body: StokvelPayoutOrderRequest): Promise<void> => {
      await sdk.stokvels.setPayoutOrder({
        path: { stokvel_id: stokvelId },
        body,
        throwOnError: true,
      })
    },
  }),
  /** `POST /stokvels/{id}/cycles` (#232): one round per current member,
   * in payout order. Pending invitations lapse. */
  startCycle: (stokvelId: string) => ({
    mutationFn: async (body: StokvelCycleStartRequest): Promise<void> => {
      await sdk.stokvels.startStokvelCycle({
        path: { stokvel_id: stokvelId },
        body,
        throwOnError: true,
      })
    },
  }),
  /** `POST /stokvels/{id}/members/me/continuation` (#237): continue into
   * the next cycle (keeping the payout beneficiary, or with a new one), or
   * leave the stokvel for good. */
  continueOrLeave: (stokvelId: string) => ({
    mutationFn: async (
      body: StokvelContinuationRequest
    ): Promise<StokvelContinuationRead> => {
      const { data } = await sdk.stokvels.continueOrLeaveStokvel({
        path: { stokvel_id: stokvelId },
        body,
        throwOnError: true,
      })
      return data
    },
  }),
  /** `POST /invitations/{id}/decline` (#230). */
  declineInvitation: () => ({
    mutationFn: async (invitationId: string): Promise<void> => {
      await sdk.stokvels.declineStokvelInvitation({
        path: { invitation_id: invitationId },
        throwOnError: true,
      })
    },
  }),
  /** `POST /invitations/{id}/revoke` (#297): the Organiser takes back a
   * pending invitation; the person can be invited again. */
  revokeInvitation: () => ({
    mutationFn: async (invitationId: string): Promise<void> => {
      await sdk.stokvels.revokeStokvelInvitation({
        path: { invitation_id: invitationId },
        throwOnError: true,
      })
    },
  }),
}

/** Every invitation of the stokvel (#375), the ones waiting for an answer
 * first; otherwise newest first, as the API sends them. */
export function invitationsByStatus(
  detail: Pick<StokvelDetailRead, "invitations">
): StokvelDetailRead["invitations"] {
  const pending = pendingInvitations(detail)
  return [
    ...pending,
    ...detail.invitations.filter((invitation) => !pending.includes(invitation)),
  ]
}

/** Invitations still waiting for an answer. */
export function pendingInvitations(
  detail: Pick<StokvelDetailRead, "invitations">
): StokvelDetailRead["invitations"] {
  return detail.invitations.filter(
    (invitation) => invitation.status === InvitationStatus.pending
  )
}

/**
 * The Organiser's beneficiaries the invite card offers: those with an
 * account in the Stokvel currency, which they'd pay from, and not already a
 * member. `otherCurrency` counts the ones left out for the currency, so the
 * card can say why they're missing.
 */
export function invitableBeneficiaries(
  beneficiaries: readonly BeneficiaryRead[],
  detail: Pick<StokvelDetailRead, "currency" | "members">
): { invitable: BeneficiaryRead[]; otherCurrency: number } {
  const members = new Set(detail.members.map((m) => m.user_id))
  const candidates = beneficiaries.filter((b) => !members.has(b.linked_user_id))
  const invitable = candidates.filter((b) =>
    b.payout_currencies.includes(detail.currency)
  )
  return { invitable, otherCurrency: candidates.length - invitable.length }
}

/**
 * Whether the Organiser can invite now: the stokvel is being set up and has
 * a free place. Pending invitations don't hold places (the cap is checked
 * when someone accepts, #230), so only current members count.
 */
export function canInvite(
  detail: Pick<
    StokvelDetailRead,
    "phase" | "is_organiser" | "member_count" | "max_members" | "deactivated_at"
  >
): boolean {
  return (
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

/** The order the Organiser has entered for the next cycle (D3): the forming
 * cycle's `payout_order` (#236), empty until entered. Index = round. */
export function plannedPayoutOrder(
  detail: Pick<StokvelDetailRead, "cycle">
): string[] {
  return detail.cycle?.status === CycleStatus.forming
    ? detail.cycle.payout_order
    : []
}

/** A member's first name; #236 sends no name when there's no first name. */
export function firstNameOf(
  member: Pick<StokvelMemberRead, "full_name">
): string {
  return member.full_name?.split(" ")[0] ?? "A member"
}

/** Why the Organiser can't start the cycle yet, in the order to fix them
 * (#232's `too_few_members` and `cycle_not_ready`); empty when it can. */
export function startCycleBlockers(
  detail: Pick<
    StokvelDetailRead,
    "members" | "cycle" | "phase" | "my_beneficiary"
  > &
    Partial<Pick<StokvelDetailRead, "previous_cycle" | "invitations">>,
  order: readonly string[] = plannedPayoutOrder(detail)
): string[] {
  if (detail.phase !== CycleStatus.forming) return []
  const blockers: string[] = []
  const going = goingIntoCycle(detail)
  const waiting = detail.invitations
    ? pendingInvitations({ invitations: detail.invitations })
    : []
  // Pending invitations count toward the people the Organiser is setting up,
  // but they are not members until they accept.
  if (going.length + waiting.length < 2) {
    blockers.push("A cycle needs at least 2 members.")
  }
  // The Organiser arranges the order from the invite list before everyone
  // has accepted. Starting still needs each of those invitations accepted;
  // the API would otherwise lapse them.
  if (waiting.length > 0) {
    const names = waiting.map(
      (invitation) => invitation.invitee_name ?? "someone"
    )
    blockers.push(
      names.length === 1
        ? `Wait for ${names[0]} to accept their invitation.`
        : `Wait for ${names.join(", ")} to accept their invitations.`
    )
  }
  // Other members' beneficiary choices are not on this response. A missing
  // one comes back as `cycle_not_ready` when the Organiser starts the cycle.
  const me = detail.members.find((member) => member.is_me)
  if (me && detail.my_beneficiary == null) {
    blockers.push("Choose your payout beneficiary.")
  }
  const everyone = new Set(going.map((m) => m.member_id))
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
  detail: Pick<StokvelDetailRead, "members" | "cycle"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>
): string[] {
  const everyone = goingIntoCycle(detail).map((m) => m.member_id)
  const kept = plannedPayoutOrder(detail).filter((id) => everyone.includes(id))
  return [...kept, ...everyone.filter((id) => !kept.includes(id))]
}

/**
 * The members going into the forming cycle: everyone for cycle 1; from
 * cycle 2 (`previous_cycle` set), the Organiser, those who chose to continue
 * and anyone who joined since (`in_cycle`, R2-15 #237). The payout order
 * must name exactly these.
 */
export function goingIntoCycle(
  detail: Pick<StokvelDetailRead, "members"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>
): StokvelMemberRead[] {
  return detail.previous_cycle
    ? detail.members.filter((member) => member.in_cycle)
    : detail.members
}

/** Members of the closed cycle who haven't said yet whether they continue.
 * Starting the next cycle treats them as leaving (#237). */
export function undecidedMembers(
  detail: Pick<StokvelDetailRead, "members"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>
): StokvelMemberRead[] {
  return detail.previous_cycle
    ? detail.members.filter((member) => !member.in_cycle)
    : []
}

/** The number of the cycle being set up: the forming cycle's own number,
 * else the one after the closed cycle. */
export function formingCycleNumber(
  detail: Pick<StokvelDetailRead, "cycle"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>
): number {
  return (
    detail.cycle?.cycle_number ?? (detail.previous_cycle?.cycle_number ?? 0) + 1
  )
}

/** Accepted invitations of `undecidedMembers`, by invitation id. Their
 * invitation was for the closed cycle, so the invitations card shows them
 * as still to answer for the next one rather than accepted. */
export function invitationsAwaitingContinuation(
  detail: Pick<StokvelDetailRead, "members" | "invitations"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>
): Set<string> {
  const undecided = new Set(undecidedMembers(detail).map((m) => m.user_id))
  return new Set(
    detail.invitations
      .filter(
        (invitation) =>
          invitation.status === InvitationStatus.accepted &&
          undecided.has(invitation.invitee_user_id)
      )
      .map((invitation) => invitation.invitation_id)
  )
}

/** Accepted invitations whose invitee is no longer a member: they chose to
 * leave after a cycle closed, or were left out when the next one started
 * (`members` lists current members only). Their invitation stays accepted,
 * so the invitations card shows them as declining the next cycle instead. */
export function invitationsOfFormerMembers(
  detail: Pick<StokvelDetailRead, "members" | "invitations">
): Set<string> {
  const current = new Set(detail.members.map((member) => member.user_id))
  return new Set(
    detail.invitations
      .filter(
        (invitation) =>
          invitation.status === InvitationStatus.accepted &&
          !current.has(invitation.invitee_user_id)
      )
      .map((invitation) => invitation.invitation_id)
  )
}

export type InvitationBadge = {
  label: string
  variant: "default" | "secondary" | "outline"
}

/** Accepted reads as done; the rest as answered with no member. */
const INVITATION_STATUS_BADGES: Record<
  InvitationStatus,
  "default" | "outline"
> = {
  pending: "outline",
  accepted: "default",
  declined: "outline",
  revoked: "outline",
  lapsed: "outline",
}

/**
 * The badge on each invitation in the invitations card, by invitation id.
 * An invitation still waiting for an answer, or accepted by a member of the
 * closed cycle who hasn't said whether they continue, is pending for the
 * cycle being set up. One accepted by a member who has since left reads as
 * declined for the cycle being set up: the detail doesn't say when they
 * left, so someone who left in an earlier setup is shown against this one
 * too. Any other shows its own status.
 */
export function invitationBadges(
  detail: Pick<StokvelDetailRead, "members" | "invitations" | "cycle"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>
): Map<string, InvitationBadge> {
  const deciding = invitationsAwaitingContinuation(detail)
  const left = invitationsOfFormerMembers(detail)
  const nextCycle = formingCycleNumber(detail)
  return new Map(
    detail.invitations.map((invitation): [string, InvitationBadge] => {
      const id = invitation.invitation_id
      if (invitation.status === InvitationStatus.pending || deciding.has(id)) {
        return [
          id,
          { label: `Pending for cycle ${nextCycle}`, variant: "secondary" },
        ]
      }
      if (left.has(id)) {
        return [
          id,
          {
            label: `Declined for cycle ${nextCycle}`,
            variant: INVITATION_STATUS_BADGES.declined,
          },
        ]
      }
      return [
        id,
        {
          label: INVITATION_STATUS_LABELS[invitation.status],
          variant: INVITATION_STATUS_BADGES[invitation.status],
        },
      ]
    })
  )
}

/**
 * Where the signed-in member stands after a cycle closes (R4-10, #259):
 * `none` when no cycle has closed into a forming one, `organiser` (always
 * continued, and can't leave), `continued`, or `undecided`.
 */
export type ContinuationStatus =
  "none" | "organiser" | "continued" | "undecided"

export function continuationStatus(
  detail: Pick<StokvelDetailRead, "members" | "is_organiser" | "phase"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>
): ContinuationStatus {
  if (!detail.previous_cycle || detail.phase !== CycleStatus.forming) {
    return "none"
  }
  if (detail.is_organiser) return "organiser"
  const me = detail.members.find((member) => member.is_me)
  return me?.in_cycle ? "continued" : "undecided"
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
 * The signed-in member's contribution to `round` (`open_round` when omitted),
 * ignoring failed attempts: after a failed send the member pays again, and
 * the live attempt is the one the panel follows.
 */
export function myCurrentContribution(
  detail: Pick<
    StokvelDetailRead,
    "cycle" | "contributions" | "my_member_id" | "open_round"
  >,
  round: number | null = detail.open_round
): StokvelRoundContributionRead | undefined {
  const cycle = detail.cycle
  if (!cycle || round == null) return undefined
  return detail.contributions.find(
    (c) =>
      c.cycle_id === cycle.cycle_id &&
      c.round === round &&
      c.member_id === detail.my_member_id &&
      c.status !== ContributionStatus.failed
  )
}

/** Members whose contribution to `round` of the current cycle is confirmed. */
export function paidMemberIds(
  detail: Pick<StokvelDetailRead, "cycle" | "contributions" | "open_round">,
  round: number = detail.open_round ?? 0
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
  cycle: StokvelDetailCycleRead | null
): string | null {
  if (
    !cycle ||
    cycle.status !== CycleStatus.active ||
    cycle.current_round == null
  ) {
    return null
  }
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
  detail: Pick<
    StokvelDetailRead,
    "cycle" | "contributions" | "members" | "open_round"
  >,
  round: number = detail.open_round ?? 0
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
