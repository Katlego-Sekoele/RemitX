/**
 * The create-stokvel wizard's state and rules (R4-03, #252), kept out of the
 * components so they can be tested on their own. Like the send flow, the
 * state lives in the URL's search params (`/app/stokvels/new?step=…`), so
 * browser back, a reload and the stepper's own triggers never lose it.
 *
 * `POST /stokvels` (R2-07, #229) takes only the name, currency and the
 * contribution in UCTUSD. Members join by invitation and the schedule is set
 * when the Organiser starts the cycle (R2-10, #232), so neither is chosen
 * here: both live on the setup page (#255).
 */

import type { StokvelCreateRequest } from "~/client"
import { amountToCents, MAX_AMOUNT_CENTS, toCents } from "~/lib/money"
import { normalizeAmount } from "~/lib/send"
import { CONTRIBUTION_TOKEN_DP, fiatToToken } from "~/lib/stokvels"

/** Every customer has a ZAR account from signup. */
export const DEFAULT_STOKVEL_CURRENCY = "ZAR"

/**
 * The member cap, for the wizard's "with N members" preview only: nothing
 * returns it before a stokvel exists. Once one does, screens read
 * `StokvelRead.max_members` instead. Mirrors `MAX_STOKVEL_MEMBERS` in
 * api/remitx_api/config.py (P3).
 */
export const PREVIEW_MEMBER_CAP = 3

export const CREATE_STEPS = [
  { key: "name", title: "Name" },
  { key: "amount", title: "Amount" },
  { key: "review", title: "Review" },
] as const

export type CreateStep = (typeof CREATE_STEPS)[number]["key"]

export type CreateSearch = {
  name: string
  /** As in the URL; resolve it against the user's accounts before use. */
  currency: string | null
  /** As typed, in the Stokvel currency; validated separately. */
  amount: string
  step: CreateStep | null
}

export function readCreateSearch(params: URLSearchParams): CreateSearch {
  const step = params.get("step")
  return {
    name: params.get("name") ?? "",
    currency: params.get("currency") || null,
    amount: params.get("amount") ?? "",
    step:
      step === "name" || step === "amount" || step === "review" ? step : null,
  }
}

/** Empty or default values drop their key rather than leaving `?amount=`. */
export function writeCreateSearch(
  current: CreateSearch,
  patch: Partial<CreateSearch>
): URLSearchParams {
  const next = { ...current, ...patch }
  const params = new URLSearchParams()
  if (next.name) params.set("name", next.name)
  if (next.currency && next.currency !== DEFAULT_STOKVEL_CURRENCY) {
    params.set("currency", next.currency)
  }
  if (next.amount) params.set("amount", next.amount)
  if (next.step) params.set("step", next.step)
  return params
}

/**
 * The Stokvel currency to use: the one in the URL if the organiser holds a
 * fiat account in it, otherwise ZAR. The page shows this one and the request
 * sends this one, so an unknown `?currency=` can't slip through.
 */
export function resolveCreateCurrency(
  requested: string | null,
  held: readonly string[]
): string {
  return requested && held.includes(requested)
    ? requested
    : DEFAULT_STOKVEL_CURRENCY
}

/** The step the page can show: no later step than the data allows. */
export function resolveCreateStep(
  search: CreateSearch,
  nameValid: boolean,
  amountValid: boolean
): CreateStep {
  if (!nameValid) return "name"
  if (search.step === "name") return "name"
  if (search.step === "review" && amountValid) return "review"
  return "amount"
}

export function createStepNumber(step: CreateStep): number {
  return CREATE_STEPS.findIndex((candidate) => candidate.key === step) + 1
}

/** `STOKVEL_NAME_MAX_LENGTH` in api/remitx_api/models/schemas/stokvel.py. */
export const MAX_NAME_LENGTH = 80

export function nameIssue(name: string): string | null {
  const trimmed = name.trim()
  if (!trimmed) return "Give the stokvel a name."
  if (trimmed.length > MAX_NAME_LENGTH) {
    return `Keep the name to ${MAX_NAME_LENGTH} characters.`
  }
  return null
}

/** Product's wording for Q6 (16 Oct): the fiat cost follows the live rate at
 * the moment each member pays, as in the Send flow. */
export const LIVE_RATE_HINT =
  "Your account is charged at the live rate at the moment you pay."

/** The smallest contribution worth a transfer fee; the API has the final say. */
export const MIN_CONTRIBUTION = "10.00"

export type AmountIssue = "empty" | "invalid" | "too_small" | "too_large"

export function contributionIssue(amount: string): AmountIssue | null {
  if (!amount.trim()) return "empty"
  const cents = toCents(amount)
  if (cents === null || cents <= 0n) return "invalid"
  if (cents < amountToCents(MIN_CONTRIBUTION)) return "too_small"
  if (cents > MAX_AMOUNT_CENTS) return "too_large"
  return null
}

export function contributionIssueMessage(
  issue: AmountIssue,
  currencyLabel: string
): string {
  switch (issue) {
    case "empty":
      return "Enter the amount each member pays per round."
    case "invalid":
      return "Enter an amount like 500 or 500.00."
    case "too_small":
      return `The minimum is ${currencyLabel} ${MIN_CONTRIBUTION} per member.`
    case "too_large":
      return "That amount is too large."
  }
}

/**
 * The `POST /stokvels` body, exactly the API's three fields. The Organiser
 * types the amount in the Stokvel currency; the stokvel stores a fixed UCTUSD
 * amount (D13), bought at `rate` (token units per 1 fiat, from the quote
 * preview, as the send flow prices) and rounded to the cent.
 */
export function createStokvelRequest(
  search: CreateSearch,
  currency: string,
  rate: string
): StokvelCreateRequest {
  return {
    name: search.name.trim(),
    currency: currency as StokvelCreateRequest["currency"],
    contribution_amount: fiatToToken(
      normalizeAmount(search.amount),
      rate,
      CONTRIBUTION_TOKEN_DP
    ),
  }
}
