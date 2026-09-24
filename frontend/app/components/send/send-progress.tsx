import {
  Stepper,
  StepperIndicator,
  StepperSeparator,
  StepperStatus,
  StepperTrigger,
} from "~/components/ui/stepper"
import { SEND_STEPS, stepNumber, type SendPageStep } from "~/lib/send"

/**
 * Recipient, Amount, Review, Sent. `maxStep` is the furthest step the flow
 * can reach with what's been chosen so far; Sent is never a click away, it's
 * where a confirmed transfer lands (SEND-3).
 */
export function SendProgress({
  step,
  maxStep,
  onStepChange,
}: {
  step: SendPageStep
  maxStep: number
  onStepChange: (step: SendPageStep) => void
}) {
  const active = stepNumber(step)

  return (
    <Stepper
      activeStep={active}
      stepCount={SEND_STEPS.length}
      maxStep={Math.min(maxStep, SEND_STEPS.length - 1)}
      onStepChange={(next) => {
        const target = SEND_STEPS[next - 1]?.key
        if (target && target !== "sent") onStepChange(target)
      }}
    >
      <nav aria-label="Send progress" className="flex flex-col gap-3">
        <StepperStatus>{SEND_STEPS[active - 1]?.title}</StepperStatus>
        <ol role="list" className="flex items-center gap-1">
          {SEND_STEPS.map((item, index) => (
            <li
              key={item.key}
              className={
                index === SEND_STEPS.length - 1
                  ? "flex items-center"
                  : "flex flex-1 items-center gap-1"
              }
            >
              <StepperTrigger step={index + 1}>
                <StepperIndicator />
                <span className="sr-only">{item.title}</span>
              </StepperTrigger>
              {index === SEND_STEPS.length - 1 ? null : (
                <StepperSeparator step={index + 1} />
              )}
            </li>
          ))}
        </ol>
      </nav>
    </Stepper>
  )
}
