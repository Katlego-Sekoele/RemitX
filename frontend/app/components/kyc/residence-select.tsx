import { GlobeHemisphereWestIcon } from "@phosphor-icons/react"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import type { KycReference } from "~/lib/api"
import {
  isOperatingCountry,
  operatingCountries,
  operatingCountryList,
  OUTSIDE_OPERATING_COUNTRIES,
} from "~/lib/kyc-reference"

/** The form value for a saved residence: the code, or "elsewhere" if we no
 * longer (or never did) operate there. */
export function residenceFormValue(
  reference: KycReference,
  saved: string | null | undefined
): string {
  if (!saved) return ""
  return isOperatingCountry(reference, saved)
    ? saved
    : OUTSIDE_OPERATING_COUNTRIES
}

export function UnsupportedJurisdictionNotice({
  reference,
}: {
  reference: KycReference
}) {
  return (
    <Alert>
      <GlobeHemisphereWestIcon />
      <AlertTitle>We don&apos;t operate in your country yet</AlertTitle>
      <AlertDescription>
        RemitX currently serves residents of {operatingCountryList(reference)}.
        You can&apos;t finish verification while you live elsewhere.
      </AlertDescription>
    </Alert>
  )
}

/**
 * Where the applicant lives: one of the countries RemitX operates in, or
 * "somewhere else". The API enforces the same rule; this says it up front.
 */
export function ResidenceSelect({
  id,
  reference,
  value,
  onChange,
  invalid,
}: {
  id: string
  reference: KycReference
  value: string
  onChange: (value: string) => void
  invalid?: boolean
}) {
  const items = [
    ...operatingCountries(reference).map((country) => ({
      value: country.code,
      label: country.name,
    })),
    { value: OUTSIDE_OPERATING_COUNTRIES, label: "Somewhere else" },
  ]

  return (
    <Select
      items={items}
      value={value || null}
      onValueChange={(next) => onChange(next ?? "")}
    >
      <SelectTrigger id={id} className="w-full" aria-invalid={invalid}>
        <SelectValue placeholder="Select where you live" />
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false}>
        <SelectGroup>
          {items.slice(0, -1).map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectGroup>
        <SelectSeparator />
        <SelectItem value={OUTSIDE_OPERATING_COUNTRIES}>
          Somewhere else
        </SelectItem>
      </SelectContent>
    </Select>
  )
}
