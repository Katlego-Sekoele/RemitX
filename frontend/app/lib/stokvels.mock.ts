/** Mocked stokvel API responses (R4-02, #251). Deleted by R4-09 (#258).
 *
 * One ZAR stokvel in each phase, plus one pending invitation: demo data
 * the list shows in development next to the API's own stokvels. List rows use
 * the generated `StokvelRead`; the detail follows docs/stokvel_integration.md
 * §3 and §5 until `GET /stokvels/{id}` (#236) exists. Amounts: 3
 * members × R500 (the product team's worked example). The signed-in user is
 * Sipho Khumalo.
 */

import type {
  BeneficiaryRead,
  SentStokvelInvitationRead,
  StokvelContributionRead,
  StokvelInvitationRead,
  StokvelListRead,
  StokvelRead,
} from "~/client"
import { amountToCents, fromCents, subtractMoney, sumMoney } from "~/lib/money"
import type { StokvelRoundTimes } from "~/lib/stokvel-schedule"
import {
  feeShare,
  poolAmount,
  plannedPayoutOrder,
  type StokvelContractStatusRead,
  type StokvelCycleRead,
  type StokvelDetailRead,
  type StokvelRoundContributionRead,
} from "~/lib/stokvels"

const ME = "usr_sipho"

/** A stokvel's next cycle before it starts, as #236 returns it: the order
 * entered so far and no rounds. */
function formingCycle(cycleId: string): StokvelCycleRead {
  return {
    cycle_id: cycleId,
    cycle_number: 1,
    status: "forming",
    current_round: 0,
    total_rounds: 0,
    started_at: null,
    closed_at: null,
    payout_order: [],
    rounds: [],
  }
}

const GROCERIES: StokvelDetailRead = {
  stokvel_id: "stk_8c21",
  name: "December groceries",
  currency: "ZAR",
  contribution_amount: "27.40000000",
  contribution_fiat_estimate: "500.00",
  organiser_name: "Lerato Nkosi",
  is_organiser: false,
  member_count: 3,
  max_members: 3,
  created_at: "2026-09-09T18:00:00Z",
  deactivated_at: null,
  phase: "active",
  current_round: 1,
  total_rounds: 3,
  next_payout_time: "2026-10-23T12:00:00Z",
  my_contribution_status: null,
  my_member_id: "mem_sipho",
  my_beneficiary: {
    beneficiary_id: "ben_tendai",
    full_name: "Tendai Moyo",
    payout_currency: "ZWL",
  },
  members: [
    {
      member_id: "mem_thabo",
      user_id: "usr_thabo",
      full_name: "Thabo Dlamini",
      is_organiser: false,
      is_me: false,
      joined_at: "2026-09-10T08:00:00Z",
      payout_ready: true,
    },
    {
      member_id: "mem_sipho",
      user_id: ME,
      full_name: "Sipho Khumalo",
      is_organiser: false,
      is_me: true,
      joined_at: "2026-09-10T09:30:00Z",
      payout_ready: true,
    },
    {
      member_id: "mem_lerato",
      user_id: "usr_lerato",
      full_name: "Lerato Nkosi",
      is_organiser: true,
      is_me: false,
      joined_at: "2026-09-09T18:00:00Z",
      payout_ready: true,
    },
  ],
  invitations: [],
  cycle: {
    cycle_id: "cyc_01",
    cycle_number: 1,
    status: "active",
    current_round: 1,
    total_rounds: 3,
    started_at: "2026-09-15T07:00:00Z",
    closed_at: null,
    payout_order: ["mem_thabo", "mem_sipho", "mem_lerato"],
    rounds: [
      {
        round: 0,
        start_time: "2026-09-15T07:00:00Z",
        deadline: "2026-09-25T12:00:00Z",
        payout_time: "2026-09-25T12:00:00Z",
        recipient_member_id: "mem_thabo",
        release_status: "released",
        remittance_status: "confirmed",
        remittance_id: "rem_0042_r1",
        release_tx_hash:
          "0x51a0c9e3b2f14d7a8c6e5f0b1d2a3c4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0e0",
        burn_tx_hash:
          "0x8f3a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2c21e",
        pool_fiat_amount: "1500.00",
        remittance_reference: "RX-STK-8C21-R1",
      },
      {
        round: 1,
        start_time: "2026-09-26T07:00:00Z",
        deadline: "2026-10-23T12:00:00Z",
        payout_time: "2026-10-23T12:00:00Z",
        recipient_member_id: "mem_sipho",
        release_status: "pending",
        remittance_status: null,
        remittance_id: null,
        release_tx_hash: null,
        burn_tx_hash: null,
        pool_fiat_amount: null,
        remittance_reference: null,
      },
      {
        round: 2,
        start_time: "2026-10-24T07:00:00Z",
        deadline: "2026-11-20T12:00:00Z",
        payout_time: "2026-11-20T12:00:00Z",
        recipient_member_id: "mem_lerato",
        release_status: null,
        remittance_status: null,
        remittance_id: null,
        release_tx_hash: null,
        burn_tx_hash: null,
        pool_fiat_amount: null,
        remittance_reference: null,
      },
    ],
  },
  contributions: [
    ...["mem_thabo", "mem_sipho", "mem_lerato"].map((memberId, i) => ({
      contribution_id: `con_r1_${i}`,
      cycle_id: "cyc_01",
      round: 0,
      member_id: memberId,
      amount_fiat: "500.00",
      amount_token: "27.40000000",
      fee_amount: "7.50",
      status: "confirmed" as const,
      evm_tx_hash: `0x${(i + 1).toString(16).padStart(64, "a")}`,
      created_at: "2026-09-20T10:00:00Z",
    })),
    {
      contribution_id: "con_r2_0",
      cycle_id: "cyc_01",
      round: 1,
      member_id: "mem_thabo",
      amount_fiat: "500.00",
      amount_token: "27.40000000",
      fee_amount: "7.50",
      status: "confirmed",
      evm_tx_hash: `0x${"b".repeat(64)}`,
      created_at: "2026-10-13T09:12:00Z",
    },
    {
      contribution_id: "con_r2_1",
      cycle_id: "cyc_01",
      round: 1,
      member_id: "mem_lerato",
      amount_fiat: "500.00",
      amount_token: "27.40000000",
      fee_amount: "7.50",
      status: "confirmed",
      evm_tx_hash: `0x${"c".repeat(64)}`,
      created_at: "2026-10-14T16:40:00Z",
    },
  ],
  partial: false,
}

const TAXI_FUND: StokvelDetailRead = {
  stokvel_id: "stk_77e0",
  name: "Taxi fund",
  currency: "ZAR",
  contribution_amount: "16.44000000",
  contribution_fiat_estimate: "300.00",
  organiser_name: "Sipho Khumalo",
  is_organiser: true,
  member_count: 2,
  max_members: 3,
  created_at: "2026-10-12T11:00:00Z",
  deactivated_at: null,
  phase: "forming",
  current_round: null,
  total_rounds: null,
  next_payout_time: null,
  my_contribution_status: null,
  my_member_id: "mem_sipho_taxi",
  my_beneficiary: null,
  members: [
    {
      member_id: "mem_sipho_taxi",
      user_id: ME,
      full_name: "Sipho Khumalo",
      is_organiser: true,
      is_me: true,
      joined_at: "2026-10-12T11:00:00Z",
      payout_ready: false,
    },
    {
      member_id: "mem_naledi_taxi",
      user_id: "usr_naledi",
      full_name: "Naledi Mokoena",
      is_organiser: false,
      is_me: false,
      joined_at: "2026-10-13T08:15:00Z",
      payout_ready: true,
    },
  ],
  invitations: [
    {
      invitation_id: "inv_bongani",
      stokvel_id: "stk_77e0",
      account_reference: "bongani1-zar",
      invitee_name: "Bongani Z.",
      status: "pending",
      created_at: "2026-10-14T07:30:00Z",
    },
  ],
  cycle: formingCycle("cyc_taxi_01"),
  contributions: [],
  partial: false,
}

const SCHOOL_FEES: StokvelDetailRead = {
  stokvel_id: "stk_02bd",
  name: "School fees 2026",
  currency: "ZAR",
  contribution_amount: "27.40000000",
  contribution_fiat_estimate: "500.00",
  organiser_name: "Lerato Nkosi",
  is_organiser: false,
  member_count: 3,
  max_members: 3,
  created_at: "2026-06-20T09:00:00Z",
  deactivated_at: null,
  phase: "closed",
  current_round: 2,
  total_rounds: 3,
  next_payout_time: null,
  my_contribution_status: "confirmed",
  my_member_id: "mem_sipho_sf",
  my_beneficiary: {
    beneficiary_id: "ben_tendai",
    full_name: "Tendai Moyo",
    payout_currency: "ZWL",
  },
  members: [],
  invitations: [],
  cycle: {
    cycle_id: "cyc_sf_01",
    cycle_number: 1,
    status: "closed",
    current_round: 2,
    total_rounds: 3,
    started_at: "2026-07-01T07:00:00Z",
    closed_at: "2026-09-12T12:05:00Z",
    payout_order: ["mem_thabo_sf", "mem_sipho_sf", "mem_lerato_sf"],
    rounds: [],
  },
  contributions: [],
  partial: false,
}

const DETAILS: Record<string, StokvelDetailRead> = {
  [GROCERIES.stokvel_id]: GROCERIES,
  [TAXI_FUND.stokvel_id]: TAXI_FUND,
  [SCHOOL_FEES.stokvel_id]: SCHOOL_FEES,
}

const FAMILY_SUPPORT_INVITATION: StokvelInvitationRead = {
  invitation_id: "inv_family",
  stokvel_id: "stk_1a9f",
  stokvel_name: "Family support",
  currency: "ZAR",
  contribution_amount: "13.70000000",
  invited_by_name: "Naledi M.",
  created_at: "2026-10-14T18:20:00Z",
}

/** The `GET /stokvels` row: exactly the backend's `StokvelRead` fields. */
function summaryOf(detail: StokvelDetailRead): StokvelRead {
  return {
    stokvel_id: detail.stokvel_id,
    name: detail.name,
    currency: detail.currency,
    contribution_amount: detail.contribution_amount,
    is_organiser: detail.is_organiser,
    member_count: detail.member_count,
    max_members: detail.max_members,
    created_at: detail.created_at,
    deactivated_at: detail.deactivated_at,
  }
}

/** A short pause so loading states show while the screens are built. Reads
 * return copies, so a later write to the store is a new object to React
 * Query and the page re-renders. */
function settle<T>(value: T, delayMs = 250): Promise<T> {
  return new Promise((resolve) =>
    setTimeout(() => resolve(structuredClone(value)), delayMs)
  )
}

/** Shaped like `ApiError` (lib/api.ts) without importing the client. */
function apiError(message: string, status: number, code?: string): Error {
  return Object.assign(new Error(message), {
    name: "ApiError",
    status,
    body: code ? { code, detail: message } : { detail: message },
  })
}

/** Knobs for the states the screens must show (doc §6, product docx §7).
 * The stokvel page exposes them in development only. */
export const stokvelMockScenario = {
  paused: false,
  /** The member's available balance in the Stokvel currency. */
  available_balance: "1240.00",
  /** How long a submitted contribution takes to confirm on chain. */
  confirm_delay_ms: 1200,
}

export function resetStokvelMockScenario() {
  stokvelMockScenario.paused = false
  stokvelMockScenario.available_balance = "1240.00"
  stokvelMockScenario.confirm_delay_ms = 1200
  // Bring back the demo invitation once it has been accepted or declined.
  MY_INVITATIONS.splice(0, MY_INVITATIONS.length, FAMILY_SUPPORT_INVITATION)
  resetInvitees()
}

/** Demo invitations to the signed-in user that they haven't answered. */
const MY_INVITATIONS: StokvelInvitationRead[] = [FAMILY_SUPPORT_INVITATION]

/** Demo rows for the list, in development only. */
export function demoStokvelsMock(): Promise<StokvelListRead> {
  return settle({
    stokvels: Object.values(DETAILS).map(summaryOf),
    invitations: MY_INVITATIONS,
  })
}

/** Rejects like the client does for an unknown id (404). */
export function getStokvelMock(stokvelId: string): Promise<StokvelDetailRead> {
  const detail = DETAILS[stokvelId]
  if (!detail) {
    return Promise.reject(new Error("Stokvel not found"))
  }
  return settle(detail)
}

export function getStokvelContractStatusMock(): Promise<StokvelContractStatusRead> {
  return settle({
    // contracts/deployments/xrplEvmTestnet.json
    address: "0x2f240705314BB79780522635eA47d20072CB8Fe1",
    network: "XRPL EVM Testnet",
    paused: false,
    treasury_token_balance: "110000.00000000",
  })
}

/** The mock's fee on a round's pool, as FSE's: R15 + 0.5% of the pool, no
 * margin (demo recipients are paid in the Stokvel currency). */
function mockFeeShare(detail: StokvelDetailRead): string {
  const pool = poolAmount(
    detail.contribution_fiat_estimate,
    detail.member_count
  )
  const fee = fromCents(1500n + (amountToCents(pool) + 100n) / 200n)
  return feeShare(fee, "0", detail.member_count)
}

/**
 * `POST /stokvels/{id}/contributions` (#233) followed by the worker's
 * confirmation (#234): the contribution is `pending`, then `confirmed` with
 * a hash. The member pays the contribution plus a fee share on top (D6).
 * Refusals use the doc §6 codes and the API's own messages.
 */
export async function contributeMock(
  stokvelId: string
): Promise<StokvelContributionRead> {
  const detail = DETAILS[stokvelId]
  if (!detail) throw apiError("Stokvel not found.", 404)
  if (stokvelMockScenario.paused) {
    throw apiError("Stokvels are temporarily paused.", 503, "stokvel_paused")
  }
  const cycle = detail.cycle
  if (!cycle || cycle.status !== "active") {
    throw apiError(
      "This stokvel has no active cycle right now.",
      409,
      "cycle_not_open"
    )
  }
  const round = cycle.current_round
  const already = detail.contributions.some(
    (c) =>
      c.cycle_id === cycle.cycle_id &&
      c.round === round &&
      c.member_id === detail.my_member_id &&
      c.status !== "failed"
  )
  if (already) {
    throw apiError(
      "You've already paid for this round.",
      409,
      "contribution_already_paid"
    )
  }
  const fee = mockFeeShare(detail)
  const needed = sumMoney([detail.contribution_fiat_estimate, fee])
  const available = stokvelMockScenario.available_balance
  if (amountToCents(available) < amountToCents(needed)) {
    throw apiError(
      `Your available ${detail.currency} balance is ${available}, and this contribution needs ${needed}. Top up your ${detail.currency} account first.`,
      400
    )
  }
  const now = new Date().toISOString()
  const entry: StokvelRoundContributionRead = {
    contribution_id: `con_${Date.now().toString(36)}`,
    cycle_id: cycle.cycle_id,
    round,
    member_id: detail.my_member_id,
    amount_fiat: detail.contribution_fiat_estimate,
    amount_token: detail.contribution_amount,
    fee_amount: fee,
    status: "pending",
    evm_tx_hash: null,
    created_at: now,
  }
  detail.contributions.push(entry)
  detail.my_contribution_status = "pending"
  stokvelMockScenario.available_balance = subtractMoney(available, needed)
  await settle(null, stokvelMockScenario.confirm_delay_ms)
  entry.status = "confirmed"
  entry.evm_tx_hash = `0x${entry.contribution_id
    .replace(/[^a-z0-9]/g, "")
    .padEnd(64, "d")}`
  detail.my_contribution_status = "confirmed"
  // The API answers `pending` at once; the mock answers after confirming so
  // the page's poll has something to show.
  return {
    contribution_id: entry.contribution_id,
    stokvel_id: stokvelId,
    cycle_number: cycle.cycle_number,
    round,
    status: "confirmed",
    currency: detail.currency,
    amount_token: entry.amount_token,
    amount_fiat: entry.amount_fiat,
    fee_amount: fee,
    amount_zar: needed,
    created_at: now,
  }
}

/**
 * People the demo can find by account reference, one per refusal the invite
 * form must explain. References follow the app's `<name><n>-<currency>`
 * format.
 */
const DIRECTORY: Record<
  string,
  { user_id: string; name: string; currency: string; verified: boolean }
> = {
  "sipho1-zar": {
    user_id: ME,
    name: "Sipho K.",
    currency: "ZAR",
    verified: true,
  },
  "thandi2-zar": {
    user_id: "usr_thandi",
    name: "Thandi N.",
    currency: "ZAR",
    verified: true,
  },
  "bongani1-zar": {
    user_id: "usr_bongani",
    name: "Bongani Z.",
    currency: "ZAR",
    verified: true,
  },
  "naledi1-zar": {
    user_id: "usr_naledi",
    name: "Naledi M.",
    currency: "ZAR",
    verified: true,
  },
  "tendai1-zwl": {
    user_id: "usr_tendai",
    name: "Tendai M.",
    currency: "ZWL",
    verified: true,
  },
  "zola1-zar": {
    user_id: "usr_zola",
    name: "Zola D.",
    currency: "ZAR",
    verified: false,
  },
  // Unverified and in another currency: the API reports the currency first.
  "nomsa1-usd": {
    user_id: "usr_nomsa",
    name: "Nomsa K.",
    currency: "USD",
    verified: false,
  },
}

/** Which demo user each sent invitation is for, to spot a repeat invite. */
const INVITEE_OF: Record<string, string> = { inv_bongani: "usr_bongani" }

function resetInvitees() {
  for (const key of Object.keys(INVITEE_OF)) delete INVITEE_OF[key]
  INVITEE_OF.inv_bongani = "usr_bongani"
}

/**
 * `POST /stokvels/{id}/invitations` (#230) on a demo stokvel, refusing as
 * the API does: the codes and wording of doc §6 "Refusals for invitations".
 */
export async function inviteMock(
  stokvelId: string,
  body: { account_reference: string }
): Promise<SentStokvelInvitationRead> {
  await settle(null)
  // The controller's order (StokvelInvitationController.invite): the caller
  // and the stokvel, then the reference, then the invitee.
  const detail = DETAILS[stokvelId]
  if (!detail) throw apiError("Stokvel not found.", 404)
  if (!detail.is_organiser) {
    throw apiError(
      "Only the stokvel's organiser can invite members.",
      403,
      "not_organiser"
    )
  }
  if (detail.deactivated_at !== null) {
    throw apiError(
      "This stokvel is no longer active.",
      409,
      "stokvel_deactivated"
    )
  }
  // An exact match, as the API does; the form lower-cases first.
  const reference = body.account_reference.trim()
  const person = DIRECTORY[reference]
  if (!person) {
    throw apiError(`No account has the reference '${reference}'.`, 404)
  }
  if (person.user_id === ME) {
    throw apiError("You can't invite yourself.", 400)
  }
  if (person.currency !== detail.currency) {
    throw apiError(
      `The account's currency must match the stokvel's currency (${detail.currency}).`,
      422,
      "invitee_currency_mismatch"
    )
  }
  if (!person.verified) {
    throw apiError(
      "This person isn't verified yet, so they can't be invited.",
      403,
      "invitee_not_verified"
    )
  }
  if (detail.members.some((member) => member.user_id === person.user_id)) {
    throw apiError(
      "This person is already a member of the stokvel.",
      409,
      "already_a_member"
    )
  }
  if (detail.member_count >= detail.max_members) {
    throw apiError(
      `A stokvel can have at most ${detail.max_members} members.`,
      422,
      "too_many_members"
    )
  }
  const pending = detail.invitations.filter((i) => i.status === "pending")
  if (pending.some((i) => INVITEE_OF[i.invitation_id] === person.user_id)) {
    throw apiError(
      "This person already has a pending invitation.",
      409,
      "invitation_already_pending"
    )
  }
  const invitation: SentStokvelInvitationRead = {
    invitation_id: `inv_${Date.now().toString(36)}`,
    stokvel_id: stokvelId,
    account_reference: reference,
    invitee_name: person.name,
    status: "pending",
    created_at: new Date().toISOString(),
  }
  INVITEE_OF[invitation.invitation_id] = person.user_id
  detail.invitations.push(invitation)
  return structuredClone(invitation)
}

function takeMyInvitation(invitationId: string): StokvelInvitationRead {
  const index = MY_INVITATIONS.findIndex(
    (invitation) => invitation.invitation_id === invitationId
  )
  if (index === -1) {
    throw apiError(
      "This invitation has already been answered or has expired.",
      409,
      "invitation_not_pending"
    )
  }
  return MY_INVITATIONS.splice(index, 1)[0]
}

/** `POST /invitations/{id}/accept` (#230) on a demo invitation: the caller
 * joins and the stokvel is now on their list. */
export async function acceptInvitationMock(
  invitationId: string
): Promise<StokvelRead> {
  await settle(null)
  const invitation = takeMyInvitation(invitationId)
  const now = new Date().toISOString()
  const myMemberId = `mem_sipho_${invitation.stokvel_id}`
  const detail: StokvelDetailRead = {
    stokvel_id: invitation.stokvel_id,
    name: invitation.stokvel_name,
    currency: invitation.currency,
    contribution_amount: invitation.contribution_amount,
    is_organiser: false,
    member_count: 2,
    max_members: 3,
    created_at: invitation.created_at,
    deactivated_at: null,
    contribution_fiat_estimate: "250.00",
    organiser_name: "Naledi Mokoena",
    phase: "forming",
    current_round: null,
    total_rounds: null,
    next_payout_time: null,
    my_contribution_status: null,
    my_member_id: myMemberId,
    my_beneficiary: null,
    members: [
      {
        member_id: `mem_naledi_${invitation.stokvel_id}`,
        user_id: "usr_naledi",
        full_name: "Naledi Mokoena",
        is_organiser: true,
        is_me: false,
        joined_at: invitation.created_at,
        payout_ready: true,
      },
      {
        member_id: myMemberId,
        user_id: ME,
        full_name: "Sipho Khumalo",
        is_organiser: false,
        is_me: true,
        joined_at: now,
        payout_ready: false,
      },
    ],
    invitations: [],
    cycle: formingCycle(`cyc_${invitation.stokvel_id}`),
    contributions: [],
    partial: false,
  }
  DETAILS[detail.stokvel_id] = detail
  return structuredClone(summaryOf(detail))
}

/** `POST /invitations/{id}/decline` (#230) on a demo invitation. */
export async function declineInvitationMock(
  invitationId: string
): Promise<void> {
  await settle(null)
  takeMyInvitation(invitationId)
}

function formingDetail(stokvelId: string): StokvelDetailRead {
  const detail = DETAILS[stokvelId]
  if (!detail) throw apiError("Stokvel not found.", 404)
  if (detail.phase !== "forming") {
    throw apiError(
      "The payout order and beneficiaries are locked while a cycle is running.",
      409,
      "cycle_locked"
    )
  }
  return detail
}

/** `PUT /stokvels/{id}/members/me/beneficiary` (#231) on a demo stokvel:
 * the pool goes to this beneficiary in their saved payout currency. */
export async function setMyBeneficiaryMock(
  stokvelId: string,
  beneficiary: Pick<
    BeneficiaryRead,
    "beneficiary_id" | "full_name" | "payout_currency"
  >
): Promise<void> {
  await settle(null)
  const detail = formingDetail(stokvelId)
  detail.my_beneficiary = {
    beneficiary_id: beneficiary.beneficiary_id,
    full_name: beneficiary.full_name ?? "your beneficiary",
    payout_currency: beneficiary.payout_currency,
  }
  const me = detail.members.find((member) => member.is_me)
  if (me) me.payout_ready = true
}

/** `PUT /stokvels/{id}/payout-order` (#231) on a demo stokvel: every
 * current member exactly once (D3). */
export async function setPayoutOrderMock(
  stokvelId: string,
  body: { member_ids: string[] }
): Promise<void> {
  await settle(null, 150)
  const detail = formingDetail(stokvelId)
  if (!detail.is_organiser) {
    throw apiError(
      "Only the stokvel's organiser can set the payout order.",
      403,
      "not_organiser"
    )
  }
  const everyone = new Set(detail.members.map((member) => member.member_id))
  const order = body.member_ids
  if (new Set(order).size !== order.length) {
    throw apiError(
      "Each member can appear only once in the payout order.",
      422,
      "invalid_payout_order"
    )
  }
  if (
    order.length !== everyone.size ||
    !order.every((memberId) => everyone.has(memberId))
  ) {
    throw apiError(
      "The payout order must include every current member.",
      422,
      "invalid_payout_order"
    )
  }
  // As #231: the first order call opens the cycle if there isn't one yet.
  detail.cycle ??= formingCycle(`cyc_${stokvelId}`)
  detail.cycle.payout_order = [...order]
}

/**
 * `POST /stokvels/{id}/cycles` (#232, as in #348) on a demo stokvel: starts
 * the cycle with the members in payout order, one round each. Pending
 * invitations lapse; members, order and beneficiaries lock.
 */
export async function startCycleMock(
  stokvelId: string,
  body: { rounds: StokvelRoundTimes[] }
): Promise<void> {
  await settle(null, 600)
  const detail = DETAILS[stokvelId]
  if (!detail) throw apiError("Stokvel not found.", 404)
  if (!detail.is_organiser) {
    throw apiError(
      "Only the stokvel's organiser can start the cycle.",
      403,
      "not_organiser"
    )
  }
  if (detail.phase !== "forming") {
    throw apiError(
      "This stokvel's cycle has already started.",
      409,
      "cycle_in_progress"
    )
  }
  if (detail.members.length < 2) {
    throw apiError("A cycle needs at least 2 members.", 409, "too_few_members")
  }
  const order = plannedPayoutOrder(detail)
  const waiting = detail.members.find((member) => !member.payout_ready)
  if (waiting || order.length !== detail.members.length) {
    throw apiError(
      "Every member needs a place in the payout order and a payout beneficiary first.",
      409,
      "cycle_not_ready"
    )
  }
  if (body.rounds.length !== order.length) {
    throw apiError("Plan one round for each member.", 422, "invalid_schedule")
  }
  for (const invitation of detail.invitations) {
    if (invitation.status === "pending") invitation.status = "lapsed"
  }
  detail.cycle = {
    cycle_id: detail.cycle?.cycle_id ?? `cyc_${Date.now().toString(36)}`,
    cycle_number: 1,
    status: "active",
    current_round: 0,
    total_rounds: order.length,
    started_at: new Date().toISOString(),
    closed_at: null,
    payout_order: [...order],
    rounds: body.rounds.map((round, i) => ({
      ...round,
      round: i,
      recipient_member_id: order[i],
      release_status: i === 0 ? "pending" : null,
      remittance_status: null,
      remittance_id: null,
      release_tx_hash: null,
      burn_tx_hash: null,
      pool_fiat_amount: null,
      remittance_reference: null,
    })),
  }
  detail.phase = "active"
  detail.current_round = 0
  detail.total_rounds = order.length
  detail.next_payout_time = body.rounds[0]?.payout_time ?? null
}

/**
 * Development only: everyone invited to a demo stokvel accepts and picks a
 * beneficiary, so the Organiser can reach Start cycle in a demo. Removed
 * with the mock in R4-09.
 */
export async function simulateInviteesAcceptMock(
  stokvelId: string
): Promise<number> {
  await settle(null, 0)
  const detail = DETAILS[stokvelId]
  if (!detail) return 0
  let joined = 0
  for (const invitation of detail.invitations) {
    if (invitation.status !== "pending") continue
    if (detail.members.length >= detail.max_members) break
    invitation.status = "accepted"
    detail.members.push({
      member_id: `mem_${invitation.invitation_id}`,
      user_id: INVITEE_OF[invitation.invitation_id] ?? invitation.invitation_id,
      full_name: invitation.invitee_name ?? invitation.account_reference,
      is_organiser: false,
      is_me: false,
      joined_at: new Date().toISOString(),
      payout_ready: true,
    })
    joined++
  }
  detail.member_count = detail.members.length
  return joined
}
