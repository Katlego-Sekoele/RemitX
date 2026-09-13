import type { KycCountry, KycIdentityScheme, KycReference } from "~/lib/api"

export const KYC_REFERENCE_KEY = ["kyc", "reference"] as const

/** The select value for "I live in a country RemitX does not serve". */
export const OUTSIDE_OPERATING_COUNTRIES = "elsewhere"

export function countryName(
  reference: KycReference | undefined,
  code: string | null | undefined
): string {
  if (!code) return "—"
  return (
    reference?.countries.find((country) => country.code === code)?.name ?? code
  )
}

export function operatingCountries(reference: KycReference): KycCountry[] {
  return reference.countries.filter((country) => country.operates_in)
}

/** "South Africa and United States" — for copy that names where we operate. */
export function operatingCountryList(reference: KycReference): string {
  const names = operatingCountries(reference).map((country) => country.name)
  if (names.length <= 2) return names.join(" and ")
  return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`
}

export function isOperatingCountry(
  reference: KycReference,
  code: string | null | undefined
): boolean {
  return operatingCountries(reference).some((country) => country.code === code)
}

/**
 * Mirrors the API: the issuing country's own scheme for the type, else the
 * any-country fallback, else nothing. The API still decides; this only
 * chooses what to show.
 */
export function resolveScheme(
  reference: KycReference,
  issuingCountry: string,
  idType: string
): KycIdentityScheme | undefined {
  const ofType = reference.identity_schemes.filter(
    (scheme) => scheme.id_type === idType
  )
  return (
    ofType.find((scheme) => scheme.country === issuingCountry) ??
    ofType.find((scheme) => scheme.country === null)
  )
}

/** One scheme per ID type the issuing country accepts, national ID first. */
export function schemesForCountry(
  reference: KycReference,
  issuingCountry: string
): KycIdentityScheme[] {
  const types = [
    ...new Set(reference.identity_schemes.map((scheme) => scheme.id_type)),
  ].sort((left, right) =>
    left === "national_id" ? -1 : right === "national_id" ? 1 : 0
  )
  return types
    .map((idType) => resolveScheme(reference, issuingCountry, idType))
    .filter((scheme): scheme is KycIdentityScheme => scheme !== undefined)
}

export function numberLabel(scheme: KycIdentityScheme | undefined): string {
  if (!scheme) return "ID number"
  return /number/i.test(scheme.label) ? scheme.label : `${scheme.label} number`
}
