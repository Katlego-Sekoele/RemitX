import { useQueryClient } from "@tanstack/react-query"
import { useMutation } from "~/hooks/use-mutation"
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
import { Button } from "~/components/ui/button"
import { DatePicker } from "~/components/ui/date-picker"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
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
import { joinedMemberIds, type RosterPerson } from "~/lib/stokvel-setup"
import {
  invalidateStokvels,
  pendingInvitations,
  startCycleBlockers,
  stokvelMutations,
  undecidedMembers,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/**
 * Schedule state for the setup wizard. Kept above the step so leaving the
 * schedule step doesn't clear the dates. In demo mode (#370) payouts are 5
 * minutes apart from Start cycle, worked out when Start is pressed.
 */
export function useCyclePlan(rounds: number) {
  const [frequency, setFrequency] = useState<Frequency>("monthly")
  const [firstPayout, setFirstPayout] = useState("")
  const [time, setTime] = useState(DEFAULT_PAYOUT_TIME)
  const [payBy, setPayBy] = useState(DEFAULT_PAY_BY_DAYS)
  const [touched, setTouched] = useState(false)
  const demo = frequency === "demo"
  const payByOptions = payByChoices(frequency)
  const payByItems = payByOptions.options.map((value) => ({
    value: String(value),
    label: payByOptions.label(value),
  }))
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    if (!demo) return
    const timer = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(timer)
  }, [demo])

  const payoutProblem = demo ? null : firstPayoutIssue(firstPayout, time)
  function scheduleFor(at: Date) {
    const first = demo
      ? demoFirstPayout(at)
      : firstPayoutDate(firstPayout, time)
    if (!first || payoutProblem) return null
    if (rounds < 1) return null
    return generateSchedule({
      firstPayout: first,
      frequency,
      rounds,
      payByBefore: payBy,
      now: at,
    })
  }
  const schedule = scheduleFor(now)
  const problems = schedule ? scheduleIssues(schedule) : []

  function chooseFrequency(next: Frequency) {
    if ((next === "demo") !== demo) {
      setPayBy(payByChoices(next).fallback)
    }
    setNow(new Date())
    setFrequency(next)
  }

  return {
    frequency,
    chooseFrequency,
    firstPayout,
    setFirstPayout,
    time,
    setTime,
    payBy,
    setPayBy,
    touched,
    setTouched,
    demo,
    payByItems,
    now,
    payoutProblem,
    scheduleFor,
    schedule,
    problems,
    ready: schedule !== null && problems.length === 0,
  }
}

export type CyclePlan = ReturnType<typeof useCyclePlan>

export function CycleScheduleFields({ plan }: { plan: CyclePlan }) {
  return (
    <FieldGroup>
      <Field>
        <FieldLabel>How often</FieldLabel>
        <RadioGroup
          value={plan.frequency}
          onValueChange={(next) => plan.chooseFrequency(next as Frequency)}
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

      {plan.demo ? (
        <FieldDescription>
          The first payout is {DEMO_INTERVAL_MINUTES} minutes after you press
          Start cycle, then one every {DEMO_INTERVAL_MINUTES} minutes. For
          demos.
        </FieldDescription>
      ) : (
        <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <Field data-invalid={plan.touched && plan.payoutProblem !== null}>
            <FieldLabel htmlFor="cycle-first-payout">
              First payout day
            </FieldLabel>
            <DatePicker
              id="cycle-first-payout"
              value={plan.firstPayout}
              range="future"
              invalid={plan.touched && plan.payoutProblem !== null}
              onChange={plan.setFirstPayout}
              onBlur={() => plan.setTouched(true)}
            />
            {plan.touched && plan.payoutProblem ? (
              <FieldError>{plan.payoutProblem}</FieldError>
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
              value={plan.time}
              onChange={(event) => plan.setTime(event.target.value)}
            />
          </Field>
        </div>
      )}

      <Field>
        <FieldLabel htmlFor="cycle-pay-by">Members pay by</FieldLabel>
        <Select
          items={plan.payByItems}
          value={String(plan.payBy)}
          onValueChange={(next) => {
            if (next !== null) plan.setPayBy(Number(next))
          }}
        >
          <SelectTrigger id="cycle-pay-by" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            {plan.payByItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <FieldDescription>
          {plan.demo ? "A reminder time" : "A reminder date"} with no penalty.
          If someone pays late, the payout waits for them.
        </FieldDescription>
      </Field>
    </FieldGroup>
  )
}

export function CycleRoundPreview({
  plan,
  roster,
}: {
  plan: CyclePlan
  roster: readonly RosterPerson[]
}) {
  if (!plan.schedule) return null
  return (
    <div className="flex flex-col gap-2">
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
            {plan.schedule.map((round, index) => (
              <TableRow key={round.payout_time}>
                <TableCell>{index + 1}</TableCell>
                <TableCell>{roster[index]?.name ?? "A member"}</TableCell>
                <TableCell>
                  {format(
                    new Date(round.deadline),
                    plan.demo ? "HH:mm" : "EEE d MMM"
                  )}
                </TableCell>
                <TableCell>
                  {format(new Date(round.payout_time), "EEE d MMM, HH:mm")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {plan.problems.length > 0 ? (
        <Alert variant="destructive">
          <AlertTitle>These dates don&apos;t work</AlertTitle>
          <AlertDescription>{plan.problems.join(" ")}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}

/** Start cycle, after the order and the schedule. Saves the joined members'
 * order first, in the place the invite list put them. */
export function CycleStartCard({
  stokvel,
  roster,
  plan,
}: {
  stokvel: StokvelDetailRead
  roster: readonly RosterPerson[]
  plan: CyclePlan
}) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const memberIds = joinedMemberIds(roster)
  const blockers = startCycleBlockers(stokvel, memberIds)
  const lapsing = pendingInvitations(stokvel).length
  const undecided = undecidedMembers(stokvel)
  const canStart = blockers.length === 0 && plan.ready && lapsing === 0

  // Two requests, one toast. The global toast would announce the wrapper too.
  const start = useMutation({
    toast: false,
    mutationFn: async () => {
      const rounds = plan.demo ? plan.scheduleFor(new Date()) : plan.schedule
      if (!rounds) return
      toast.loading("Starting the cycle…", {
        id: `start-${stokvel.stokvel_id}`,
      })
      await stokvelMutations
        .setPayoutOrder(stokvel.stokvel_id)
        .mutationFn({ member_ids: memberIds })
      await stokvelMutations
        .startCycle(stokvel.stokvel_id)
        .mutationFn({ rounds })
    },
    onSuccess: async () => {
      setConfirming(false)
      await invalidateStokvels(queryClient)
      toast.success(`${stokvel.name} has started`, {
        id: `start-${stokvel.stokvel_id}`,
      })
    },
    onError: (error) => {
      toast.error(stokvelErrorMessage(error), {
        id: `start-${stokvel.stokvel_id}`,
      })
    },
  })

  return (
    <>
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

      <div className="flex justify-end">
        <Button
          disabled={!canStart}
          onClick={() => {
            plan.setTouched(true)
            if (canStart) setConfirming(true)
          }}
        >
          Start cycle
        </Button>
      </div>

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
    </>
  )
}
