/** Mocked stokvel API responses (R4-02, #251). Deleted by R4-09 (#258).
 *
 * One ZAR stokvel in each phase, plus one pending invitation, shaped like
 * docs/stokvel_integration.md §3 and §5. Amounts: 3 members × R500 (the
 * product team's worked example). The signed-in user is Sipho Khumalo.
 */

import type {
  StokvelContractStatusRead,
  StokvelDetailRead,
  StokvelListRead,
} from "~/lib/stokvels"

const ME = "usr_sipho"

const GROCERIES: StokvelDetailRead = {
  stokvel_id: "stk_8c21",
  name: "December groceries",
  goal: "Groceries for the family in December",
  currency: "ZAR",
  contribution_amount: "27.40000000",
  contribution_fiat_estimate: "500.00",
  organiser_name: "Lerato Nkosi",
  is_organiser: false,
  member_count: 3,
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
      status: "confirmed",
      evm_tx_hash: `0x${"c".repeat(64)}`,
      created_at: "2026-10-14T16:40:00Z",
    },
  ],
}

const TAXI_FUND: StokvelDetailRead = {
  stokvel_id: "stk_77e0",
  name: "Taxi fund",
  goal: null,
  currency: "ZAR",
  contribution_amount: "16.44000000",
  contribution_fiat_estimate: "300.00",
  organiser_name: "Sipho Khumalo",
  is_organiser: true,
  member_count: 2,
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
      stokvel_name: "Taxi fund",
      organiser_name: "Sipho Khumalo",
      currency: "ZAR",
      contribution_fiat_estimate: "300.00",
      member_count: 2,
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
  goal: "Term fees",
  currency: "ZAR",
  contribution_amount: "27.40000000",
  contribution_fiat_estimate: "500.00",
  organiser_name: "Lerato Nkosi",
  is_organiser: false,
  member_count: 3,
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

const FAMILY_SUPPORT_INVITATION = {
  invitation_id: "inv_family",
  stokvel_id: "stk_1a9f",
  stokvel_name: "Family support",
  organiser_name: "Naledi Mokoena",
  currency: "ZAR",
  contribution_fiat_estimate: "250.00",
  member_count: 3,
  status: "pending" as const,
  created_at: "2026-10-14T18:20:00Z",
}

function summaryOf(detail: StokvelDetailRead) {
  const {
    my_member_id: _me,
    my_beneficiary: _beneficiary,
    members: _members,
    invitations: _invitations,
    cycle: _cycle,
    contributions: _contributions,
    ...summary
  } = detail
  return summary
}

/** A short pause so loading states show while the screens are built. */
function settle<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 250))
}

export function listStokvelsMock(): Promise<StokvelListRead> {
  return settle({
    stokvels: Object.values(DETAILS).map(summaryOf),
    invitations: [FAMILY_SUPPORT_INVITATION],
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
