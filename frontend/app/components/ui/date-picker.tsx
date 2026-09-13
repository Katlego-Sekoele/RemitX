import { useState } from "react"
import { CalendarBlankIcon } from "@phosphor-icons/react"
import { format, isValid, parse } from "date-fns"

import { Button } from "~/components/ui/button"
import { Calendar } from "~/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "~/components/ui/popover"

const ISO_DATE = "yyyy-MM-dd"

type DatePickerProps = {
  id?: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  required?: boolean
  disabled?: boolean
  invalid?: boolean
  /** "past" (default) for a birth date; "future" for an expiry date. */
  range?: "past" | "future"
}

function parseIsoDate(value: string): Date | undefined {
  if (!value) return undefined
  const parsed = parse(value, ISO_DATE, new Date())
  return isValid(parsed) ? parsed : undefined
}

/** Popover + Calendar date field. Stores ISO `yyyy-MM-dd` like a date input. */
export function DatePicker({
  id,
  value,
  onChange,
  placeholder = "Select date",
  required,
  disabled,
  invalid,
  range = "past",
}: DatePickerProps) {
  const [open, setOpen] = useState(false)
  const selected = parseIsoDate(value)
  const now = new Date()
  const future = range === "future"

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        disabled={disabled}
        render={
          <Button
            id={id}
            type="button"
            variant="outline"
            className="w-full justify-start font-normal data-[empty=true]:text-muted-foreground"
            data-empty={!selected}
            aria-required={required}
            aria-invalid={invalid}
          />
        }
      >
        <CalendarBlankIcon aria-hidden="true" />
        {selected ? format(selected, "PPP") : <span>{placeholder}</span>}
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          captionLayout="dropdown"
          startMonth={
            future
              ? new Date(now.getFullYear(), now.getMonth())
              : new Date(now.getFullYear() - 100, 0)
          }
          endMonth={
            future
              ? new Date(now.getFullYear() + 15, 11)
              : new Date(now.getFullYear(), 11)
          }
          // An expiry has to be after today; a birth date cannot be after it.
          disabled={
            future
              ? {
                  before: new Date(
                    now.getFullYear(),
                    now.getMonth(),
                    now.getDate() + 1
                  ),
                }
              : { after: now }
          }
          onSelect={(date) => {
            onChange(date ? format(date, ISO_DATE) : "")
            setOpen(false)
          }}
        />
      </PopoverContent>
    </Popover>
  )
}
