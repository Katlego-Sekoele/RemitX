import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router"
import { toast } from "sonner"

import { InviteMemberForm } from "~/components/stokvels/invite-member-form"
import { PayoutBeneficiaryCard } from "~/components/stokvels/payout-beneficiary-card"
import { PayoutOrderList } from "~/components/stokvels/payout-order-list"
import {
  CycleRoundPreview,
  CycleScheduleFields,
  CycleStartCard,
  useCyclePlan,
} from "~/components/stokvels/cycle-setup"
import { StokvelInvitations } from "~/components/stokvels/stokvel-invitations"
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
import {
  Stepper,
  StepperIndicator,
  StepperSeparator,
  StepperStatus,
  StepperTrigger,
} from "~/components/ui/stepper"
import { stokvelErrorMessage } from "~/lib/stokvel-errors"
import {
  arrangeRoster,
  clampSetupStep,
  cycleRoster,
  joinedMemberIds,
  readRosterDraft,
  savedRosterOrder,
  sameIds,
  SETUP_STEPS,
  setupMaxStep,
  setupStepByNumber,
  setupStepNumber,
  writeRosterDraft,
  type RosterPerson,
  type SetupStep,
} from "~/lib/stokvel-setup"
import {
  canInvite,
  goingIntoCycle,
  invalidateStokvels,
  pendingInvitations,
  startCycleBlockers,
  stokvelMutations,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/**
 * Organiser setup while the cycle is forming: invite, arrange the invite
 * list, set the schedule, then start. Later steps stay closed until the
 * earlier ones allow them. Start stays closed until every invite has been
 * accepted.
 */
export function SetupWizard({ stokvel }: { stokvel: StokvelDetailRead }) {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [roster, setRoster] = useState<RosterPerson[]>(() =>
    arrangeRoster(
      cycleRoster(stokvel),
      savedRosterOrder(stokvel),
      readRosterDraft(stokvel.stokvel_id)
    )
  )

  useEffect(() => {
    setRoster((current) =>
      arrangeRoster(
        cycleRoster(stokvel),
        savedRosterOrder(stokvel),
        current.map((person) => person.key)
      )
    )
  }, [stokvel])

  const savedKey = savedRosterOrder(stokvel).join(",")
  const memberKey = joinedMemberIds(roster).join(",")
  useEffect(() => {
    const saved = savedKey === "" ? [] : savedKey.split(",")
    const memberIds = memberKey === "" ? [] : memberKey.split(",")
    const newcomers = memberIds.filter((id) => !saved.includes(id))
    if (saved.length === 0 || newcomers.length === 0) return
    if (sameIds(memberIds, saved)) return
    const toastId = `payout-order-${stokvel.stokvel_id}`
    toast.loading("Saving payout order…", { id: toastId })
    void stokvelMutations
      .setPayoutOrder(stokvel.stokvel_id)
      .mutationFn({ member_ids: memberIds })
      .then(async () => {
        await invalidateStokvels(queryClient)
        toast.success("Payout order saved", { id: toastId })
      })
      .catch((error: unknown) => {
        toast.error(stokvelErrorMessage(error), { id: toastId })
      })
  }, [memberKey, queryClient, savedKey, stokvel.stokvel_id])

  const plan = useCyclePlan(roster.length)
  const memberIds = useMemo(() => joinedMemberIds(roster), [roster])
  const blockers = startCycleBlockers(stokvel, memberIds)
  const maxStep = setupMaxStep({
    rosterCount: roster.length,
    scheduleReady: plan.ready,
    canStart: blockers.length === 0 && plan.ready,
  })
  const requested = params.get("setup") ?? "people"
  const step = clampSetupStep(requested, maxStep)

  useEffect(() => {
    if (step === requested || (requested === "people" && step === "people")) {
      return
    }
    const next = new URLSearchParams(params)
    next.set("setup", step)
    setParams(next, { replace: true })
  }, [params, requested, setParams, step])

  function go(next: SetupStep) {
    const copy = new URLSearchParams(params)
    copy.set("setup", next)
    setParams(copy, { replace: true })
  }

  function reorder(next: RosterPerson[]) {
    setRoster(next)
    writeRosterDraft(
      stokvel.stokvel_id,
      next.map((person) => person.key)
    )
  }

  const waiting = pendingInvitations(stokvel).length
  const joined = goingIntoCycle(stokvel).length
  const active = setupStepNumber(step)

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]">
      <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:order-last">
        <Card>
          <CardHeader>
            <CardTitle>Setup</CardTitle>
            <CardDescription>
              {waiting === 0
                ? "Everyone you've invited has joined."
                : `${waiting} still to accept. You can arrange their place in this tab while you wait.`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Stepper
              activeStep={active}
              stepCount={SETUP_STEPS.length}
              maxStep={maxStep}
              onStepChange={(next) => go(setupStepByNumber(next))}
            >
              <nav aria-label="Stokvel setup" className="flex flex-col gap-3">
                <StepperStatus>{SETUP_STEPS[active - 1]?.title}</StepperStatus>
                <ol role="list" className="flex items-center gap-1">
                  {SETUP_STEPS.map((item, index) => (
                    <li
                      key={item.key}
                      className={
                        index === SETUP_STEPS.length - 1
                          ? "flex items-center"
                          : "flex flex-1 items-center gap-1"
                      }
                    >
                      <StepperTrigger step={index + 1}>
                        <StepperIndicator />
                        <span className="sr-only">{item.title}</span>
                      </StepperTrigger>
                      {index === SETUP_STEPS.length - 1 ? null : (
                        <StepperSeparator step={index + 1} />
                      )}
                    </li>
                  ))}
                </ol>
              </nav>
            </Stepper>
          </CardContent>
        </Card>
        <PayoutBeneficiaryCard stokvel={stokvel} />
      </aside>

      <div className="flex min-w-0 flex-col gap-4">
        {joined < 2 || waiting > 0 ? (
          <Alert>
            <AlertTitle>
              {joined} of {joined + waiting} joined
            </AlertTitle>
            <AlertDescription>
              You can start the stokvel cycle once at least 2 members, you
              included, have joined.
            </AlertDescription>
          </Alert>
        ) : null}
        {step === "people" ? (
          <>
            {canInvite(stokvel) ? <InviteMemberForm stokvel={stokvel} /> : null}
            <StokvelInvitations stokvel={stokvel} />
            <StepNav
              onBack={null}
              onNext={() => go("order")}
              nextDisabled={roster.length < 2}
              nextHint={
                roster.length < 2 ? "Invite at least one person." : null
              }
            />
          </>
        ) : null}

        {step === "order" ? (
          <Card>
            <CardHeader>
              <CardTitle>Payout order</CardTitle>
              <CardDescription>
                One round per person: everyone pays in, and one person is paid
                out. Put the list in the order you agreed.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <PayoutOrderList
                stokvel={stokvel}
                roster={roster}
                onReorder={reorder}
              />
            </CardContent>
            <CardFooter className="justify-between gap-2">
              <Button variant="outline" onClick={() => go("people")}>
                Back
              </Button>
              <Button onClick={() => go("schedule")}>Next</Button>
            </CardFooter>
          </Card>
        ) : null}

        {step === "schedule" ? (
          <Card>
            <CardHeader>
              <CardTitle>Schedule</CardTitle>
              <CardDescription>
                When each round opens, when members should pay, and when the
                pool is paid out.
                {waiting > 0
                  ? " You can set this now. Starting waits until everyone has joined."
                  : ""}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-6">
              <CycleScheduleFields plan={plan} />
              <CycleRoundPreview plan={plan} roster={roster} />
            </CardContent>
            <CardFooter className="flex-wrap justify-between gap-2">
              <Button variant="outline" onClick={() => go("order")}>
                Back
              </Button>
              <div className="flex items-center gap-3">
                {plan.ready && blockers[0] ? (
                  <p className="text-sm text-muted-foreground">{blockers[0]}</p>
                ) : null}
                <Button
                  disabled={!plan.ready || blockers.length > 0}
                  onClick={() => {
                    plan.setTouched(true)
                    if (plan.ready && blockers.length === 0) go("start")
                  }}
                >
                  Next
                </Button>
              </div>
            </CardFooter>
          </Card>
        ) : null}

        {step === "start" ? (
          <Card>
            <CardHeader>
              <CardTitle>Start the cycle</CardTitle>
              <CardDescription>
                Membership, the payout order and everyone&apos;s beneficiary
                lock until the cycle ends.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <CycleRoundPreview plan={plan} roster={roster} />
              <CycleStartCard stokvel={stokvel} roster={roster} plan={plan} />
            </CardContent>
            <CardFooter>
              <Button variant="outline" onClick={() => go("schedule")}>
                Back
              </Button>
            </CardFooter>
          </Card>
        ) : null}
      </div>
    </div>
  )
}

function StepNav({
  onBack,
  onNext,
  nextDisabled,
  nextHint,
}: {
  onBack: (() => void) | null
  onNext: () => void
  nextDisabled: boolean
  nextHint: string | null
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      {onBack ? (
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
      ) : (
        <span />
      )}
      <div className="flex items-center gap-3">
        {nextHint ? (
          <p className="text-sm text-muted-foreground">{nextHint}</p>
        ) : null}
        <Button disabled={nextDisabled} onClick={onNext}>
          Next
        </Button>
      </div>
    </div>
  )
}
