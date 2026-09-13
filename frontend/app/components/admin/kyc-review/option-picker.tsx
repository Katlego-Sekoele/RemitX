import { CaretDownIcon } from "@phosphor-icons/react"

import { humanise } from "~/components/admin/kyc-review/format"
import { Button } from "~/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"

export type PickerOption = { value: string; description: string }

/** One catalogue row — a reason code or a rating — with its description, so
 * the reviewer picks by meaning rather than by code. */
export function OptionPicker({
  id,
  options,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  id?: string
  options: readonly PickerOption[]
  value: string
  onChange: (next: string) => void
  placeholder: string
  disabled?: boolean
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            id={id}
            variant="outline"
            className="w-full justify-between"
            disabled={disabled}
          />
        }
      >
        <span className="truncate first-letter:uppercase">
          {value ? humanise(value) : placeholder}
        </span>
        <CaretDownIcon data-icon="inline-end" />
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuRadioGroup
          value={value}
          onValueChange={(next) => onChange(String(next))}
        >
          {options.map((option) => (
            <DropdownMenuRadioItem key={option.value} value={option.value}>
              <span className="flex flex-col gap-0.5 py-0.5">
                <span className="font-medium first-letter:uppercase">
                  {humanise(option.value)}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {option.description}
                </span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
