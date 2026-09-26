import type { QueryClient } from "@tanstack/react-query"

import { api, type BeneficiaryRead, type PayoutCurrency } from "~/client"

export type BeneficiarySort = "newest" | "alphabetical"

export const BENEFICIARY_SORT_LABELS: Record<BeneficiarySort, string> = {
  newest: "Newest",
  alphabetical: "A–Z",
}

export type BeneficiaryNameSource = {
  full_name?: string | null
}

/** Fiat payout currencies this beneficiary can receive: the accounts they
 * hold, plus their saved default when it is no longer in that list. */
export function beneficiaryPayoutCurrencies(
  beneficiary: Pick<BeneficiaryRead, "payout_currency" | "payout_currencies">
): readonly PayoutCurrency[] {
  const held = beneficiary.payout_currencies
  return held.includes(beneficiary.payout_currency)
    ? held
    : [beneficiary.payout_currency, ...held]
}

/** What to call a beneficiary: their verified name, or their sign-up first
 * name until they are verified. */
export function beneficiaryName(beneficiary: BeneficiaryNameSource): string {
  return beneficiary.full_name?.trim() || "Unnamed recipient"
}

/** First name and last initial, e.g. "Tendai M.", for confirmations. */
export function beneficiaryShortName(
  beneficiary: BeneficiaryNameSource
): string {
  const words = (beneficiary.full_name ?? "").trim().split(/\s+/)
  if (words.length >= 2) {
    return `${words[0]} ${words[words.length - 1][0].toUpperCase()}.`
  }
  return words[0] || "this recipient"
}

/** Up to two initials, from the first and last words of the name. */
export function beneficiaryInitials(
  beneficiary: BeneficiaryNameSource
): string {
  const words = (beneficiary.full_name ?? "").trim().split(/\s+/)
  const first = words[0]?.[0] ?? ""
  const last = words.length > 1 ? (words[words.length - 1]?.[0] ?? "") : ""
  return (first + last).toUpperCase() || "?"
}

/** "sibling" -> "Sibling". */
export function relationshipLabel(relationship: string): string {
  return relationship.charAt(0).toUpperCase() + relationship.slice(1)
}

/** The masked contact line, e.g. "t•••@gmail.com · +2637••••••23". */
export function maskedContact(beneficiary: BeneficiaryRead): string | null {
  const parts = [
    beneficiary.masked_email,
    beneficiary.masked_mobile_number,
  ].filter(Boolean)
  return parts.length > 0 ? parts.join(" · ") : null
}

/** Refetch every sorted copy of the list after an add, edit or remove. The
 * key without a `query` matches each sort's key. */
export function invalidateBeneficiaries(queryClient: QueryClient) {
  return queryClient.invalidateQueries({
    queryKey: api.beneficiaries.listMyBeneficiaries().queryKey,
  })
}
