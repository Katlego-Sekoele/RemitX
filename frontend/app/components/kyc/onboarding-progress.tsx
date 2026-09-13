import { useNavigate } from "react-router"

import {
  Stepper,
  StepperIndicator,
  StepperSeparator,
  StepperStatus,
  StepperTrigger,
} from "~/components/ui/stepper"
import type { KycOnboardingStepRead as KycOnboardingStep } from "~/client"
import { applicationStepPath } from "~/lib/kyc-onboarding"

const STEP_TITLES: Record<string, string> = {
  identity: "About you",
  "id-document": "Identification",
  address: "Address",
  contact: "Contact",
  financial: "Financial profile",
  declarations: "Declarations",
  review: "Review",
}

function titleFor(step: string) {
  return STEP_TITLES[step] ?? step.replaceAll("-", " ")
}

/**
 * The wizard's progress. The server's `next_step` is the furthest step an
 * applicant may jump to; everything before it has been saved.
 */
export function OnboardingProgress({
  applicationId,
  steps,
  current,
  nextStep,
}: {
  applicationId: string
  steps: KycOnboardingStep[]
  current: string
  nextStep: string
}) {
  const navigate = useNavigate()
  const trail = steps.filter(
    (step) => step.role === "collect" || step.role === "review"
  )
  const activeIndex = Math.max(
    0,
    trail.findIndex((step) => step.step === current)
  )
  const nextIndex = trail.findIndex((step) => step.step === nextStep)
  const reachable = nextIndex < 0 ? trail.length : nextIndex + 1

  return (
    <Stepper
      activeStep={activeIndex + 1}
      stepCount={trail.length}
      maxStep={reachable}
      onStepChange={(step) => {
        const target = trail[step - 1]
        if (target) navigate(applicationStepPath(applicationId, target.step))
      }}
    >
      <nav aria-label="Onboarding progress" className="flex flex-col gap-3">
        <StepperStatus>
          {titleFor(trail[activeIndex]?.step ?? current)}
        </StepperStatus>
        <ol role="list" className="flex items-center gap-1">
          {trail.map((step, index) => (
            <li
              key={step.step}
              className={
                index === trail.length - 1
                  ? "flex items-center"
                  : "flex flex-1 items-center gap-1"
              }
            >
              <StepperTrigger step={index + 1}>
                <StepperIndicator />
                <span className="sr-only">{titleFor(step.step)}</span>
              </StepperTrigger>
              {index === trail.length - 1 ? null : (
                <StepperSeparator step={index + 1} />
              )}
            </li>
          ))}
        </ol>
      </nav>
    </Stepper>
  )
}
