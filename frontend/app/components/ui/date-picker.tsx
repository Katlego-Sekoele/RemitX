import { useState } from "react"
import { CalendarBlankIcon } from "@phosphor-icons/react"
import { format, isValid, parse } from "date-fns"

import { Calendar } from "~/components/ui/calendar"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "~/components/ui/input-group"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "~/components/ui/popover"

const ISO_DATE = "yyyy-MM-dd"

type DatePart = "day" | "month" | "year"

// The browser locale decides the typed format: 13/09/2026, 09/13/2026,
// 2026/09/13, 13.09.2026, ...
const localeFormat = new Intl.DateTimeFormat(undefined, {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
})

const localeParts = localeFormat.formatToParts(new Date(2000, 11, 31))

const partOrder = localeParts
  .map((part) => part.type)
  .filter((type): type is DatePart => ["day", "month", "year"].includes(type))

const localePlaceholder = localeParts
  .map((part) =>
    part.type === "day"
      ? "DD"
      : part.type === "month"
        ? "MM"
        : part.type === "year"
          ? "YYYY"
          : part.value
  )
  .join("")

type DatePickerProps = {
  id?: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
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

function formatLocaleDate(date: Date | undefined): string {
  return date ? localeFormat.format(date) : ""
}

/** Reads typed text in the locale's day/month/year order. */
function parseLocaleDate(text: string): Date | undefined {
  const numbers = text.trim().split(/\D+/).filter(Boolean)
  if (numbers.length !== 3) return undefined
  const parts = Object.fromEntries(
    partOrder.map((part, index) => [part, Number(numbers[index])])
  ) as Record<DatePart, number>
  if (String(parts.year).length !== 4) return undefined
  const date = new Date(parts.year, parts.month - 1, parts.day)
  // Rejects rollovers such as 31/02 becoming 3 March.
  return date.getFullYear() === parts.year &&
    date.getMonth() === parts.month - 1 &&
    date.getDate() === parts.day
    ? date
    : undefined
}

/** Typeable date field with a calendar popover. Stores ISO `yyyy-MM-dd`. */
export function DatePicker({
  id,
  value,
  onChange,
  onBlur,
  required,
  disabled,
  invalid,
  range = "past",
}: DatePickerProps) {
  const [open, setOpen] = useState(false)
  const selected = parseIsoDate(value)
  const [text, setText] = useState(formatLocaleDate(selected))
  const [month, setMonth] = useState(selected)
  const [syncedValue, setSyncedValue] = useState(value)
  const now = new Date()
  const future = range === "future"

  // A value set from outside (reset, prefill) replaces the typed text.
  if (value !== syncedValue) {
    setSyncedValue(value)
    setText(formatLocaleDate(selected))
    setMonth(selected)
  }

  function emit(next: string) {
    setSyncedValue(next)
    onChange(next)
  }

  return (
    <InputGroup>
      <InputGroupInput
        id={id}
        value={text}
        placeholder={localePlaceholder}
        inputMode="numeric"
        autoComplete="off"
        disabled={disabled}
        required={required}
        aria-invalid={invalid}
        onChange={(event) => {
          const date = parseLocaleDate(event.target.value)
          setText(event.target.value)
          if (date) setMonth(date)
          emit(date ? format(date, ISO_DATE) : "")
        }}
        onBlur={() => {
          if (selected) setText(formatLocaleDate(selected))
          onBlur?.()
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault()
            setOpen(true)
          }
        }}
      />
      <InputGroupAddon align="inline-end">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger
            disabled={disabled}
            render={
              <InputGroupButton
                variant="ghost"
                size="icon-xs"
                aria-label="Select date"
              />
            }
          >
            <CalendarBlankIcon aria-hidden="true" />
          </PopoverTrigger>
          <PopoverContent
            className="w-auto overflow-hidden p-0"
            align="end"
            alignOffset={-8}
            sideOffset={10}
          >
            <Calendar
              mode="single"
              selected={selected}
              month={month}
              onMonthChange={setMonth}
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
                setText(formatLocaleDate(date))
                emit(date ? format(date, ISO_DATE) : "")
                onBlur?.()
                setOpen(false)
              }}
            />
          </PopoverContent>
        </Popover>
      </InputGroupAddon>
    </InputGroup>
  )
}
