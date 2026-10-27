import { ArrowDownIcon, ArrowUpIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { format } from "date-fns"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog"
import { Badge } from "~/components/ui/badge"
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
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldTitle,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { RadioGroup, RadioGroupItem } from "~/components/ui/radio-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import {
  DEFAULT_PAY_BY_DAYS,
  DEMO_INTERVAL_MINUTES,
  demoFirstPayout,
  DEFAULT_PAYOUT_TIME,
  firstPayoutDate,
  firstPayoutIssue,
  FREQUENCIES,
  generateSchedule,
  payByChoices,
  scheduleIssues,
  type Frequency,
} from "~/lib/stokvel-schedule"
import { stokvelErrorMessage } from "~/lib/stokvel-errors"
import {
  invalidateStokvels,
  moveInOrder,
  payoutOrderWithEveryone,
  undecidedMembers,
  pendingInvitations,
  startCycleBlockers,
  stokvelMutations,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/**
 * The Organiser's setup before a cycle (R4-06, #255): the payout order the
 * members agreed off the platform (D3), the schedule, and Start cycle. Each
 * round has a pay-by date and a payout time (Q4 B); the pay-by date is a
 * reminder with no penalty (D7), the payout waits for every member (D12).
 * Starting locks membership, order and beneficiaries until the cycle ends.
 * In demo mode (#370) payouts are 5 minutes apart from Start cycle, and the
 * schedule is worked out when Start is pressed, so time spent on the screen
 * can't push the first payout into the past.
 */
export function CycleSetup({ stokvel }: { stokvel: StokvelDetailRead }) {
  const queryClient = useQueryClient()
  const [frequency, setFrequency] = useState<Frequency>("monthly")
  const [firstPayout, setFirstPayout] = useState("")
  const [time, setTime] = useState(DEFAULT_PAYOUT_TIME)
  // Days before each payout, or minutes in demo mode.
  const [payBy, setPayBy] = useState(DEFAULT_PAY_BY_DAYS)
  const [touched, setTouched] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const demo = frequency === "demo"
  const payByOptions = payByChoices(frequency)
  const payByItems = payByOptions.options.map((value) => ({
    value: String(value),
    label: payByOptions.label(value),
  }))
  // The demo preview shows the times as if Start were pressed now.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    if (!demo) return
    const timer = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(timer)
  }, [demo])

  const order = payoutOrderWithEveryone(stokvel)
  const member = (memberId: string) =>
    stokvel.members.find((m) => m.member_id === memberId)
  const nameOf = (memberId: string) => {
    const m = member(memberId)
    return m?.is_me ? "You" : (m?.full_name ?? "A member")
  }

  const saveOrder = useMutation({
    ...stokvelMutations.setPayoutOrder(stokvel.stokvel_id),
    onSettled: () => invalidateStokvels(queryClient),
  })
  const start = useMutation({
    mutationFn: async () => {
      // Demo times are worked out now, when Start is pressed.
      const rounds = demo ? scheduleFor(new Date()) : schedule
      if (!rounds) return
      // The order shown is the one that starts, even if never reordered.
      await stokvelMutations
        .setPayoutOrder(stokvel.stokvel_id)
        .mutationFn({ member_ids: order })
      await stokvelMutations
        .startCycle(stokvel.stokvel_id)
        .mutationFn({ rounds })
    },
    onSuccess: async () => {
      setConfirming(false)
      await invalidateStokvels(queryClient)
      toast.success(`${stokvel.name} has started`)
    },
  })

  const payoutProblem = demo ? null : firstPayoutIssue(firstPayout, time)
  function scheduleFor(at: Date) {
    const first = demo
      ? demoFirstPayout(at)
      : firstPayoutDate(firstPayout, time)
    if (!first || payoutProblem) return null
    return generateSchedule({
      firstPayout: first,
      frequency,
      rounds: order.length,
      payByBefore: payBy,
      now: at,
    })
  }
  const schedule = scheduleFor(now)
  const problems = schedule ? scheduleIssues(schedule) : []
  const blockers = startCycleBlockers(stokvel, order)
  const lapsing = pendingInvitations(stokvel).length
  // From cycle 2: members who haven't said whether they continue. Starting
  // treats them as leaving (#237).
  const undecided = undecidedMembers(stokvel)
  const canStart =
    blockers.length === 0 && schedule !== null && problems.length === 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>Start the cycle</CardTitle>
        <CardDescription>
          One round per member: everyone pays in each round, and one member is
          paid out. Enter the order you agreed together.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <FieldTitle>Payout order</FieldTitle>
          <ol className="flex flex-col gap-2">
            {order.map((memberId, i) => {
              const m = member(memberId)
              return (
                <li
                  key={memberId}
                  className="flex items-center justify-between gap-2"
                >
                  <span className="flex items-center gap-2">
                    <Badge variant="outline">Round {i + 1}</Badge>
                    {nameOf(memberId)}
                    {m?.is_me && !stokvel.my_beneficiary ? (
                      <Badge variant="secondary">No beneficiary yet</Badge>
                    ) : null}
                  </span>
                  <span className="flex gap-1">
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label={`Move ${nameOf(memberId)} up`}
                      disabled={i === 0 || saveOrder.isPending}
                      onClick={() =>
                        saveOrder.mutate({
                          member_ids: moveInOrder(order, i, -1),
                        })
                      }
                    >
                      <ArrowUpIcon />
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label={`Move ${nameOf(memberId)} down`}
                      disabled={i === order.length - 1 || saveOrder.isPending}
                      onClick={() =>
                        saveOrder.mutate({
                          member_ids: moveInOrder(order, i, 1),
                        })
                      }
                    >
                      <ArrowDownIcon />
                    </Button>
                  </span>
                </li>
              )
            })}
          </ol>
          {saveOrder.isError ? (
            <FieldError>{stokvelErrorMessage(saveOrder.error)}</FieldError>
          ) : null}
        </div>

        <FieldGroup>
          <Field>
            <FieldLabel>How often</FieldLabel>
            <RadioGroup
              value={frequency}
              onValueChange={(next) => {
                const nextFrequency = next as Frequency
                // Days and minutes don't mix: "2 days" never goes as "2
                // minutes", so switching mode resets the pay-by.
                if ((nextFrequency === "demo") !== demo) {
                  setPayBy(payByChoices(nextFrequency).fallback)
                }
                setNow(new Date())
                setFrequency(nextFrequency)
              }}
              className="flex flex-wrap gap-4"
            >
              {FREQUENCIES.map((option) => (
                <div key={option.key} className="flex items-center gap-2">
                  <RadioGroupItem
                    value={option.key}
                    id={`cycle-frequency-${option.key}`}
                  />
                  <FieldLabel htmlFor={`cycle-frequency-${option.key}`}>
                    {option.label}
                  </FieldLabel>
                </div>
              ))}
            </RadioGroup>
          </Field>

          {demo ? (
            <FieldDescription>
              The first payout is {DEMO_INTERVAL_MINUTES} minutes after you
              press Start cycle, then one every {DEMO_INTERVAL_MINUTES} minutes.
              For demos.
            </FieldDescription>
          ) : (
            <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
              <Field data-invalid={touched && payoutProblem !== null}>
                <FieldLabel htmlFor="cycle-first-payout">
                  First payout day
                </FieldLabel>
                <DatePicker
                  id="cycle-first-payout"
                  value={firstPayout}
                  range="future"
                  invalid={touched && payoutProblem !== null}
                  onChange={setFirstPayout}
                  onBlur={() => setTouched(true)}
                />
                {touched && payoutProblem ? (
                  <FieldError>{payoutProblem}</FieldError>
                ) : (
                  <FieldDescription>
                    The pool is released at this time once everyone has paid.
                  </FieldDescription>
                )}
              </Field>
              <Field>
                <FieldLabel htmlFor="cycle-payout-time">Time</FieldLabel>
                <Input
                  id="cycle-payout-time"
                  type="time"
                  value={time}
                  onChange={(event) => setTime(event.target.value)}
                />
              </Field>
            </div>
          )}

          <Field>
            <FieldLabel htmlFor="cycle-pay-by">Members pay by</FieldLabel>
            <Select
              items={payByItems}
              value={String(payBy)}
              onValueChange={(next) => {
                if (next !== null) setPayBy(Number(next))
              }}
            >
              <SelectTrigger id="cycle-pay-by" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {payByItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription>
              {demo ? "A reminder time" : "A reminder date"} with no penalty. If
              someone pays late, the payout waits for them.
            </FieldDescription>
          </Field>
        </FieldGroup>

        {schedule ? (
          <div className="flex flex-col gap-2">
            <FieldTitle>Rounds</FieldTitle>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Round</TableHead>
                    <TableHead>Paid to</TableHead>
                    <TableHead>Pay by</TableHead>
                    <TableHead>Payout</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {schedule.map((round, i) => (
                    <TableRow key={round.payout_time}>
                      <TableCell>{i + 1}</TableCell>
                      <TableCell>{nameOf(order[i])}</TableCell>
                      <TableCell>
                        {format(
                          new Date(round.deadline),
                          demo ? "HH:mm" : "EEE d MMM"
                        )}
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
            {problems.length > 0 ? (
              <Alert variant="destructive">
                <AlertTitle>These dates don&apos;t work</AlertTitle>
                <AlertDescription>{problems.join(" ")}</AlertDescription>
              </Alert>
            ) : null}
          </div>
        ) : null}

        {undecided.length > 0 ? (
          <Alert>
            <AlertTitle>
              {undecided.length === 1
                ? "1 member hasn't answered"
                : `${undecided.length} members haven't answered`}
            </AlertTitle>
            <AlertDescription>
              {undecided.map((m) => m.full_name ?? "A member").join(", ")}{" "}
              {undecided.length === 1 ? "hasn't" : "haven't"} said whether
              they&apos;re continuing. If you start now, they leave the stokvel.
            </AlertDescription>
          </Alert>
        ) : null}

        {blockers.length > 0 ? (
          <Alert>
            <AlertTitle>Before you can start</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {blockers.map((blocker) => (
                  <li key={blocker}>{blocker}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
      <CardFooter className="flex-wrap justify-end gap-2">
        <Button
          disabled={!canStart}
          onClick={() => {
            setTouched(true)
            if (canStart) setConfirming(true)
          }}
        >
          Start cycle
        </Button>
      </CardFooter>

      <AlertDialog
        open={confirming}
        onOpenChange={(next) => {
          setConfirming(next)
          if (!next) start.reset()
        }}
      >
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Start {stokvel.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              The members, payout order and everyone&apos;s beneficiary are
              locked until the cycle ends.
              {lapsing > 0
                ? ` ${lapsing} open invitation${lapsing === 1 ? "" : "s"} will lapse.`
                : ""}
              {undecided.length > 0
                ? ` ${undecided.length === 1 ? "1 member who hasn't answered leaves" : `${undecided.length} members who haven't answered leave`} the stokvel.`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {start.isError ? (
            <FieldError>{stokvelErrorMessage(start.error)}</FieldError>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={start.isPending}>
              Not yet
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={start.isPending}
              onClick={() => start.mutate()}
            >
              {start.isPending ? "Starting…" : "Start cycle"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
