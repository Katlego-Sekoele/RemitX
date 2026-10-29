/** Mocked admin contract routes (R4-07, #256) until R3-07 (#244) exists.
 * Deleted by R4-09 (#258). Kept in memory, so a pause lasts until the page
 * reloads. */

import type {
  StokvelContractPauseRequest,
  StokvelContractRead,
} from "~/lib/stokvel-contract"

const INITIAL: StokvelContractRead = {
  // contracts/deployments/xrplEvmTestnet.json
  address: "0x2f240705314BB79780522635eA47d20072CB8Fe1",
  network: "XRPL EVM Testnet",
  paused: false,
  paused_at: null,
  paused_reason: null,
  treasury_token_balance: "110000.00000000",
}

let contract: StokvelContractRead = { ...INITIAL }

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

export function getStokvelContractMock(): Promise<StokvelContractRead> {
  return settle(contract, 200)
}

export async function pauseStokvelContractMock(
  body: StokvelContractPauseRequest
): Promise<StokvelContractRead> {
  await settle(null)
  if (!body.reason.trim()) {
    throw apiError("A reason is required to pause.", 422)
  }
  if (contract.paused) {
    throw apiError("Stokvels are already paused.", 409, "stokvel_paused")
  }
  contract = {
    ...contract,
    paused: true,
    paused_at: new Date().toISOString(),
    paused_reason: body.reason.trim(),
  }
  return structuredClone(contract)
}

export async function resumeStokvelContractMock(): Promise<StokvelContractRead> {
  await settle(null)
  if (!contract.paused) {
    throw apiError("Stokvels aren't paused.", 409)
  }
  contract = {
    ...contract,
    paused: false,
    paused_at: null,
    paused_reason: null,
  }
  return structuredClone(contract)
}

/** For tests: back to running. */
export function resetStokvelContractMock() {
  contract = { ...INITIAL }
}
