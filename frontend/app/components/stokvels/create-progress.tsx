import {
  Stepper,
  StepperIndicator,
  StepperSeparator,
  StepperStatus,
  StepperTrigger,
} from "~/components/ui/stepper"
import {
  CREATE_STEPS,
  createStepNumber,
  type CreateStep,
} from "~/lib/stokvel-create"

/**
 * Name, Amount and schedule, Review. `maxStep` is the furthest step the
 * wizard can reach with what has been entered so far. Invitations (#253) and
 * the payout order (#255) add their steps to `CREATE_STEPS`.
 */
export function CreateProgress({
  step,
  maxStep,
  onStepChange,
}: {
  step: CreateStep
  maxStep: number
  onStepChange: (step: CreateStep) => void
}) {
  const active = createStepNumber(step)

  return (
    <Stepper
      activeStep={active}
      stepCount={CREATE_STEPS.length}
      maxStep={Math.min(maxStep, CREATE_STEPS.length)}
      onStepChange={(next) => {
        const target = CREATE_STEPS[next - 1]?.key
        if (target) onStepChange(target)
      }}
    >
      <nav aria-label="Create stokvel progress" className="flex flex-col gap-3">
        <StepperStatus>{CREATE_STEPS[active - 1]?.title}</StepperStatus>
        <ol role="list" className="flex items-center gap-1">
          {CREATE_STEPS.map((item, index) => (
            <li
              key={item.key}
              className={
                index === CREATE_STEPS.length - 1
                  ? "flex items-center"
                  : "flex flex-1 items-center gap-1"
              }
            >
              <StepperTrigger step={index + 1}>
                <StepperIndicator />
                <span className="sr-only">{item.title}</span>
              </StepperTrigger>
              {index === CREATE_STEPS.length - 1 ? null : (
                <StepperSeparator step={index + 1} />
              )}
            </li>
          ))}
        </ol>
      </nav>
    </Stepper>
  )
}
