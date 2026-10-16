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
  SentStokvelInvitationRead,
  StokvelContributionRead,
  StokvelInvitationRead,
  StokvelListRead,
  StokvelRead,
} from "~/client"
import { amountToCents, fromCents, subtractMoney, sumMoney } from "~/lib/money"
import {
  feeShare,
  poolAmount,
  type StokvelContractStatusRead,
  type StokvelDetailRead,
  type StokvelRoundContributionRead,
} from "~/lib/stokvels"

const ME = "usr_sipho"

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
    },
    {
      member_id: "mem_sipho",
      user_id: ME,
      full_name: "Sipho Khumalo",
      is_organiser: false,
      is_me: true,
      joined_at: "2026-09-10T09:30:00Z",
    },
    {
      member_id: "mem_lerato",
      user_id: "usr_lerato",
      full_name: "Lerato Nkosi",
      is_organiser: true,
      is_me: false,
      joined_at: "2026-09-09T18:00:00Z",
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
    },
    {
      member_id: "mem_naledi_taxi",
      user_id: "usr_naledi",
      full_name: "Naledi Mokoena",
      is_organiser: false,
      is_me: false,
      joined_at: "2026-10-13T08:15:00Z",
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
  cycle: null,
  contributions: [],
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
}

/** Demo rows for the list, in development only. */
/** Demo invitations to the signed-in user that they haven't answered. */
const MY_INVITATIONS: StokvelInvitationRead[] = [FAMILY_SUPPORT_INVITATION]

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
}

/** Which demo user each sent invitation is for, to spot a repeat invite. */
const INVITEE_OF: Record<string, string> = { inv_bongani: "usr_bongani" }

/**
 * `POST /stokvels/{id}/invitations` (#230) on a demo stokvel, refusing as
 * the API does: the codes and wording of doc §6 "Refusals for invitations".
 */
export async function inviteMock(
  stokvelId: string,
  body: { account_reference: string }
): Promise<SentStokvelInvitationRead> {
  await settle(null)
  const detail = DETAILS[stokvelId]
  if (!detail) throw apiError("Stokvel not found.", 404)
  if (!detail.is_organiser) {
    throw apiError(
      "Only the stokvel's organiser can invite members.",
      403,
      "not_organiser"
    )
  }
  const reference = body.account_reference.trim().toLowerCase()
  const person = DIRECTORY[reference]
  if (!person) {
    throw apiError(`No account has the reference '${reference}'.`, 404)
  }
  if (person.user_id === ME) {
    throw apiError("You can't invite yourself.", 400)
  }
  if (!person.verified) {
    throw apiError(
      "This person isn't verified yet, so they can't be invited.",
      403,
      "invitee_not_verified"
    )
  }
  if (person.currency !== detail.currency) {
    throw apiError(
      `The account's currency must match the stokvel's currency (${detail.currency}).`,
      422,
      "invitee_currency_mismatch"
    )
  }
  if (detail.members.some((member) => member.user_id === person.user_id)) {
    throw apiError(
      "This person is already a member of the stokvel.",
      409,
      "already_a_member"
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
  if (detail.member_count >= detail.max_members) {
    throw apiError(
      `A stokvel can have at most ${detail.max_members} members.`,
      422,
      "too_many_members"
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
      },
      {
        member_id: myMemberId,
        user_id: ME,
        full_name: "Sipho Khumalo",
        is_organiser: false,
        is_me: true,
        joined_at: now,
      },
    ],
    invitations: [],
    cycle: null,
    contributions: [],
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
