"use client"

import * as React from "react"
import { createContext, useContext, useMemo } from "react"
import { GlobeSimpleIcon } from "@phosphor-icons/react"
import * as BasePhoneInput from "react-phone-number-input"
import flags from "react-phone-number-input/flags"

import { Button } from "~/components/ui/button"
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxSeparator,
  ComboboxTrigger,
  ComboboxValue,
} from "~/components/ui/combobox"
import { Input } from "~/components/ui/input"
import { cn } from "~/lib/utils"

type PhoneInputSize = "sm" | "default" | "lg"

const PhoneInputContext = createContext<{
  variant: PhoneInputSize
  popupClassName?: string
}>({
  variant: "default",
  popupClassName: undefined,
})

type PhoneInputProps = Omit<
  React.ComponentProps<"input">,
  "onChange" | "value" | "ref"
> &
  Omit<
    BasePhoneInput.Props<typeof BasePhoneInput.default>,
    "onChange" | "variant" | "popupClassName"
  > & {
    onChange?: (value: BasePhoneInput.Value) => void
    variant?: PhoneInputSize
    popupClassName?: string
  }

function PhoneInput({
  className,
  variant,
  popupClassName,
  onChange,
  value,
  ...props
}: PhoneInputProps) {
  const phoneInputSize = variant || "default"
  return (
    <PhoneInputContext.Provider
      value={{ variant: phoneInputSize, popupClassName }}
    >
      <BasePhoneInput.default
        className={cn(
          "flex w-full",
          props["aria-invalid"] &&
            "[&_*[data-slot=combobox-trigger]]:border-destructive [&_*[data-slot=combobox-trigger]]:ring-1 [&_*[data-slot=combobox-trigger]]:ring-destructive/20 dark:[&_*[data-slot=combobox-trigger]]:border-destructive/50 dark:[&_*[data-slot=combobox-trigger]]:ring-destructive/40",
          className
        )}
        flagComponent={FlagComponent}
        countrySelectComponent={CountrySelect}
        inputComponent={InputComponent}
        smartCaret={false}
        value={value || undefined}
        onChange={(next) => onChange?.(next || ("" as BasePhoneInput.Value))}
        {...props}
      />
    </PhoneInputContext.Provider>
  )
}

function InputComponent({
  className,
  ...props
}: React.ComponentProps<typeof Input>) {
  const { variant } = useContext(PhoneInputContext)

  return (
    <Input
      className={cn(
        "min-w-0 flex-1 rounded-s-none",
        variant === "sm" && "h-7",
        variant === "lg" && "h-9",
        className
      )}
      {...props}
    />
  )
}

type CountryEntry = {
  label: string
  value: BasePhoneInput.Country
}

type CountrySelectProps = {
  disabled?: boolean
  value: BasePhoneInput.Country
  options: { label: string; value: BasePhoneInput.Country | undefined }[]
  onChange: (country: BasePhoneInput.Country) => void
}

const countryLabel = (country: CountryEntry) => country.label
const countryCode = (country: CountryEntry) => country.value
const sameCountry = (left: CountryEntry, right: CountryEntry) =>
  left.value === right.value

function CountrySelect({
  disabled,
  value: selectedCountry,
  options: countryList,
  onChange,
}: CountrySelectProps) {
  const { variant, popupClassName } = useContext(PhoneInputContext)
  const countries = useMemo(
    () =>
      countryList.filter(
        (item): item is CountryEntry => item.value !== undefined
      ),
    [countryList]
  )
  const selected =
    countries.find((country) => country.value === selectedCountry) ?? null

  return (
    <Combobox
      items={countries}
      value={selected}
      onValueChange={(country) => {
        if (country?.value) onChange(country.value)
      }}
      itemToStringLabel={countryLabel}
      itemToStringValue={countryCode}
      isItemEqualToValue={sameCountry}
      autoHighlight
    >
      <ComboboxTrigger
        render={
          <Button
            variant="outline"
            size={variant}
            className="flex gap-1 rounded-e-none border-e-0 px-2.5 py-0 leading-none"
            disabled={disabled}
          >
            <span className="sr-only">
              <ComboboxValue />
            </span>
            <FlagComponent
              country={selectedCountry}
              countryName={selectedCountry}
            />
          </Button>
        }
      />
      <ComboboxContent className={cn("w-xs", popupClassName)}>
        <ComboboxInput placeholder="Search for a country" showTrigger={false} />
        <ComboboxSeparator />
        <ComboboxEmpty>No country found.</ComboboxEmpty>
        <ComboboxList>
          {(country: CountryEntry) => (
            <ComboboxItem key={country.value} value={country}>
              <FlagComponent
                country={country.value}
                countryName={country.label}
              />
              <span className="flex-1">{country.label}</span>
              <span className="text-muted-foreground">
                {`+${BasePhoneInput.getCountryCallingCode(country.value)}`}
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}

function FlagComponent({ country, countryName }: BasePhoneInput.FlagProps) {
  const Flag = flags[country]

  return (
    <span className="flex size-4 items-center justify-center overflow-hidden rounded-sm [&_svg]:size-full">
      {Flag ? (
        <Flag title={countryName} />
      ) : (
        <GlobeSimpleIcon className="size-4 text-muted-foreground" />
      )}
    </span>
  )
}

export { PhoneInput }
