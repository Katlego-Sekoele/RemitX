import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "~/components/ui/combobox"
import type { KycCountry } from "~/lib/api"

// Module-level so their identities never change between renders.
const countryLabel = (country: KycCountry) => country.name
const countryCode = (country: KycCountry) => country.code
const sameCountry = (left: KycCountry, right: KycCountry) =>
  left.code === right.code

function matches(country: KycCountry, query: string) {
  const needle = query.trim().toLowerCase()
  return (
    needle === "" ||
    country.name.toLowerCase().includes(needle) ||
    country.code.toLowerCase() === needle
  )
}

/**
 * Searchable country picker, by name or ISO code. Holds the code, so it drops
 * straight into a react-hook-form `Controller`.
 */
export function CountryCombobox({
  id,
  countries,
  value,
  onChange,
  onBlur,
  invalid,
  placeholder = "Search for a country",
}: {
  id: string
  countries: KycCountry[]
  value: string
  onChange: (code: string) => void
  onBlur?: () => void
  invalid?: boolean
  placeholder?: string
}) {
  const selected = countries.find((country) => country.code === value) ?? null

  return (
    <Combobox
      items={countries}
      value={selected}
      onValueChange={(country) => {
        const code = country?.code ?? ""
        if (code !== value) onChange(code)
      }}
      itemToStringLabel={countryLabel}
      itemToStringValue={countryCode}
      isItemEqualToValue={sameCountry}
      filter={matches}
      // Typing "zim" then Enter picks Zimbabwe.
      autoHighlight
    >
      <ComboboxInput
        id={id}
        className="w-full"
        placeholder={placeholder}
        aria-invalid={invalid}
        onBlur={onBlur}
      />
      <ComboboxContent>
        <ComboboxEmpty>No country matches that.</ComboboxEmpty>
        <ComboboxList>
          {(country: KycCountry) => (
            <ComboboxItem key={country.code} value={country}>
              {country.name}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
