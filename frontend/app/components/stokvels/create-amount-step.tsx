import { useQuery } from "@tanstack/react-query"
import { format } from "date-fns"
import { useMemo, useState } from "react"

import { sdk, type PayoutCurrency } from "~/client"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { DatePicker } from "~/components/ui/date-picker"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "~/components/ui/input-group"
import { RadioGroup, RadioGroupItem } from "~/components/ui/radio-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { useDebouncedValue } from "~/hooks/use-debounced-value"
import { errorMessage } from "~/hooks/use-onboarding"
import { currencySymbol, formatMoney } from "~/lib/money"
import {
  isPayoutCurrency,
  normalizeAmount,
  PREVIEW_DEBOUNCE_MS,
  sanitizeAmountInput,
} from "~/lib/send"
import {
  contributionIssue,
  contributionIssueMessage,
  firstPayoutIssue,
  FREQUENCIES,
  MAX_STOKVEL_MEMBERS,
  membersIssue,
  MIN_STOKVEL_MEMBERS,
  scheduleIssues,
  type CreateSearch,
  type Frequency,
} from "~/lib/stokvel-create"
import { poolAmount, type StokvelScheduleRound } from "~/lib/stokvels"

/**
 * What a round's pool costs to pay out, priced like any transfer in the
 * Stokvel currency. The exchange margin depends on each member's own payout
 * currency, so it is not in this figure. Nothing is held or saved.
 */
function usePoolPreview(pool: string, currency: string, enabled: boolean) {
  const senderAmount = normalizeAmount(pool)
  const receiver: PayoutCurrency = isPayoutCurrency(currency) ? currency : "ZAR"
  return useQuery({
    queryKey: ["quotes", "preview", senderAmount, currency, receiver],
    queryFn: async ({ signal }) => {
      const { data } = await sdk.quotes.previewQuote({
        body: {
          sender_amount: senderAmount,
          sender_currency: currency,
          receiver_payout_currency: receiver,
        },
        signal,
        throwOnError: true,
      })
      return data
    },
    enabled,
    staleTime: 30_000,
  })
}

const MEMBER_OPTIONS = Array.from(
  { length: MAX_STOKVEL_MEMBERS - MIN_STOKVEL_MEMBERS + 1 },
  (_, i) => {
    const value = String(MIN_STOKVEL_MEMBERS + i)
    return { value, label: `${value} members` }
  }
)

export function CreateAmountStep({
  search,
  currency,
  schedule,
  onChange,
  onBack,
  onContinue,
}: {
  search: CreateSearch
  currency: string
  /** Generated from the search by the page, or null while incomplete. */
  schedule: StokvelScheduleRound[] | null
  onChange: (patch: Partial<CreateSearch>) => void
  onBack: () => void
  onContinue: () => void
}) {
  const [touched, setTouched] = useState(false)
  const amountProblem = contributionIssue(search.amount)
  const membersProblem = membersIssue(search.members)
  const payoutProblem = firstPayoutIssue(search.firstPayout, search.time)
  const scheduleProblems = schedule ? scheduleIssues(schedule) : []
  const valid =
    amountProblem === null &&
    membersProblem === null &&
    payoutProblem === null &&
    scheduleProblems.length === 0

  const pool = useMemo(
    () =>
      amountProblem === null
        ? poolAmount(normalizeAmount(search.amount), search.members)
        : null,
    [amountProblem, search.amount, search.members]
  )
  const debouncedPool = useDebouncedValue(pool, PREVIEW_DEBOUNCE_MS)
  const settled = debouncedPool === pool
  const preview = usePoolPreview(
    debouncedPool ?? "0",
    currency,
    debouncedPool !== null
  )

  return (
    <Card>
      <form
        noValidate
        className="flex flex-col gap-(--card-spacing)"
        onSubmit={(event) => {
          event.preventDefault()
          setTouched(true)
          if (valid) onContinue()
        }}
      >
        <CardHeader>
          <CardTitle>Amount and schedule</CardTitle>
          <CardDescription>
            The same amount every round. Your account is charged at the live
            rate on the day you pay.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <FieldGroup>
            <Field data-invalid={touched && amountProblem !== null}>
              <FieldLabel htmlFor="stokvel-amount">
                Each member pays, per round
              </FieldLabel>
              <InputGroup>
                <InputGroupAddon>
                  <InputGroupText>{currencySymbol(currency)}</InputGroupText>
                </InputGroupAddon>
                <InputGroupInput
                  id="stokvel-amount"
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder="500.00"
                  value={search.amount}
                  aria-invalid={touched && amountProblem !== null}
                  onChange={(event) =>
                    onChange({
                      amount: sanitizeAmountInput(event.target.value),
                    })
                  }
                  onBlur={() => setTouched(true)}
                />
              </InputGroup>
              {touched && amountProblem ? (
                <FieldError>
                  {contributionIssueMessage(amountProblem, currency)}
                </FieldError>
              ) : (
                <FieldDescription>
                  Fixed for the whole stokvel. A different amount means a new
                  stokvel.
                </FieldDescription>
              )}
            </Field>

            <Field data-invalid={membersProblem !== null}>
              <FieldLabel htmlFor="stokvel-members">Members</FieldLabel>
              <Select
                items={MEMBER_OPTIONS}
                value={String(search.members)}
                onValueChange={(next) => {
                  if (next) onChange({ members: Number(next) })
                }}
              >
                <SelectTrigger id="stokvel-members" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {MEMBER_OPTIONS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {membersProblem ? (
                <FieldError>{membersProblem}</FieldError>
              ) : (
                <FieldDescription>
                  You included. One round per member; the cycle runs with
                  whoever has accepted when you start it.
                </FieldDescription>
              )}
            </Field>

            <Field>
              <FieldLabel>How often</FieldLabel>
              <RadioGroup
                value={search.frequency}
                onValueChange={(next) =>
                  onChange({ frequency: next as Frequency })
                }
                className="flex flex-wrap gap-4"
              >
                {FREQUENCIES.map((option) => (
                  <div key={option.key} className="flex items-center gap-2">
                    <RadioGroupItem
                      value={option.key}
                      id={`stokvel-frequency-${option.key}`}
                    />
                    <FieldLabel htmlFor={`stokvel-frequency-${option.key}`}>
                      {option.label}
                    </FieldLabel>
                  </div>
                ))}
              </RadioGroup>
            </Field>

            <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
              <Field data-invalid={touched && payoutProblem !== null}>
                <FieldLabel htmlFor="stokvel-first-payout">
                  First payout day
                </FieldLabel>
                <DatePicker
                  id="stokvel-first-payout"
                  value={search.firstPayout}
                  range="future"
                  invalid={touched && payoutProblem !== null}
                  onChange={(next) => onChange({ firstPayout: next })}
                  onBlur={() => setTouched(true)}
                />
                {touched && payoutProblem ? (
                  <FieldError>{payoutProblem}</FieldError>
                ) : (
                  <FieldDescription>
                    Members are asked to pay by the payout day. Each later round
                    opens the morning after the previous payout.
                  </FieldDescription>
                )}
              </Field>
              <Field>
                <FieldLabel htmlFor="stokvel-payout-time">Time</FieldLabel>
                <Input
                  id="stokvel-payout-time"
                  type="time"
                  value={search.time}
                  onChange={(event) => onChange({ time: event.target.value })}
                />
              </Field>
            </div>
          </FieldGroup>

          {schedule ? (
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium">Rounds</p>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Round</TableHead>
                      <TableHead>Opens</TableHead>
                      <TableHead>Pay by</TableHead>
                      <TableHead>Payout</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {schedule.map((round) => (
                      <TableRow key={round.round}>
                        <TableCell>{round.round + 1}</TableCell>
                        <TableCell>
                          {format(new Date(round.start_time), "EEE d MMM")}
                        </TableCell>
                        <TableCell>
                          {format(new Date(round.deadline), "EEE d MMM")}
                        </TableCell>
                        <TableCell>
                          {format(
                            new Date(round.payout_time),
                            "EEE d MMM, HH:mm"
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {scheduleProblems.length > 0 ? (
                <Alert variant="destructive">
                  <AlertTitle>Rounds must stay in order</AlertTitle>
                  <AlertDescription>
                    {scheduleProblems.join(" ")}
                  </AlertDescription>
                </Alert>
              ) : null}
            </div>
          ) : null}

          {pool ? (
            <PoolPreview
              pool={pool}
              currency={currency}
              members={search.members}
              loading={!settled || preview.isPending}
              error={preview.error}
              fee={preview.data?.sender_transaction_fee}
              sent={preview.data?.receiver_amount}
            />
          ) : null}
        </CardContent>
        <CardFooter className="flex-wrap justify-between gap-2">
          <Button type="button" variant="outline" onClick={onBack}>
            Back
          </Button>
          <Button type="submit" disabled={touched && !valid}>
            Continue
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}

/** Live preview that updates as the amount or member count changes. */
function PoolPreview({
  pool,
  currency,
  members,
  loading,
  error,
  fee,
  sent,
}: {
  pool: string
  currency: string
  members: number
  loading: boolean
  error: unknown
  fee: string | undefined
  sent: string | undefined
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-muted p-4">
      <p className="text-sm font-medium">Each round</p>
      <DescriptionList>
        <DescriptionItem>
          <DescriptionTerm>Pool ({members} members)</DescriptionTerm>
          <DescriptionDetails>{formatMoney(pool, currency)}</DescriptionDetails>
        </DescriptionItem>
        <DescriptionItem>
          <DescriptionTerm>Transfer fee, from the pool</DescriptionTerm>
          <DescriptionDetails>
            {loading ? (
              <Skeleton className="h-4 w-20" />
            ) : fee ? (
              `− ${formatMoney(fee, currency)}`
            ) : (
              "—"
            )}
          </DescriptionDetails>
        </DescriptionItem>
        <DescriptionItem>
          <DescriptionTerm>
            Sent to the member&apos;s beneficiary
          </DescriptionTerm>
          <DescriptionDetails>
            {loading ? (
              <Skeleton className="h-4 w-24" />
            ) : sent ? (
              `≈ ${formatMoney(sent, currency)}`
            ) : (
              "—"
            )}
          </DescriptionDetails>
        </DescriptionItem>
      </DescriptionList>
      <p className="text-xs text-muted-foreground">
        An exchange margin of 1% also applies when the beneficiary is paid in
        another currency, at the rate on payout day.
        {error ? ` Preview unavailable: ${errorMessage(error)}` : ""}
      </p>
    </div>
  )
}
