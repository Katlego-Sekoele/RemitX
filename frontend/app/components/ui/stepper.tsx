import { CheckIcon } from "@phosphor-icons/react"
import { createContext, useContext, type ComponentProps } from "react"
import { cn } from "cn"

/**
 * Stepper navigation, ported from creatorem's Stepper
 * (https://creatorem.com/docs/ui/components/stepper).
 *
 * Kept: the `Stepper` / `StepperTrigger` / `StepperActiveStep` /
 * `StepperStepLength` API and the `data-state="active|complete|upcoming"`
 * contract that variants style with `group-data-[state=…]/stepper-trigger`.
 *
 * Changed: the original keeps the active step in memory and renders every
 * step's content itself, via `@kit/utils/stepper`, which is not published.
 * Here the step is controlled — the caller passes `activeStep` from wherever it
 * lives (for onboarding, the URL) — and there is no StepperContent / Next /
 * Previous, because each step is its own route with its own form. Triggers
 * are real buttons, and `maxStep` replaces `disableForwardNav` so already
 * completed steps ahead of the current one stay reachable.
 */

type StepperContextValue = {
  activeStep: number
  stepCount: number
  maxStep: number
  onStepChange?: (step: number) => void
}

const StepperContext = createContext<StepperContextValue | null>(null)

function useStepper() {
  const context = useContext(StepperContext)
  if (!context) throw new Error("Stepper parts must be inside <Stepper>")
  return context
}

function Stepper({
  activeStep,
  stepCount,
  maxStep = stepCount,
  onStepChange,
  className,
  ...props
}: ComponentProps<"div"> & {
  /** 1-based. */
  activeStep: number
  stepCount: number
  /** Triggers after this step are disabled. Defaults to every step. */
  maxStep?: number
  onStepChange?: (step: number) => void
}) {
  return (
    <StepperContext.Provider
      value={{ activeStep, stepCount, maxStep, onStepChange }}
    >
      <div data-slot="stepper" className={cn(className)} {...props} />
    </StepperContext.Provider>
  )
}

function StepperTrigger({
  step,
  className,
  children,
  ...props
}: Omit<ComponentProps<"button">, "onClick" | "type"> & { step: number }) {
  const { activeStep, maxStep, onStepChange } = useStepper()
  const state =
    activeStep === step ? "active" : activeStep > step ? "complete" : "upcoming"
  const disabled = step > maxStep && step !== activeStep

  return (
    <button
      type="button"
      data-slot="stepper-trigger"
      data-state={state}
      aria-current={state === "active" ? "step" : undefined}
      disabled={disabled}
      onClick={() => {
        if (step !== activeStep) onStepChange?.(step)
      }}
      className={cn(
        "group/stepper-trigger cursor-pointer rounded-full outline-none disabled:pointer-events-none disabled:opacity-50 data-[state=active]:cursor-default",
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
}

/**
 * creatorem's circle: a check once complete, a filled dot while active, an
 * empty ring ahead. Reads the state from the enclosing `StepperTrigger`.
 */
function StepperIndicator({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      data-slot="stepper-indicator"
      className={cn(
        "relative flex size-7 shrink-0 items-center justify-center rounded-full border-2 transition-all",
        "group-data-[state=complete]/stepper-trigger:border-primary group-data-[state=complete]/stepper-trigger:bg-primary group-hover/stepper-trigger:group-data-[state=complete]/stepper-trigger:bg-primary/80",
        "group-data-[state=active]/stepper-trigger:border-primary group-data-[state=active]/stepper-trigger:bg-background",
        "group-data-[state=upcoming]/stepper-trigger:border-border group-data-[state=upcoming]/stepper-trigger:bg-background group-hover/stepper-trigger:group-data-[state=upcoming]/stepper-trigger:border-muted-foreground/30",
        "group-focus-visible/stepper-trigger:ring-2 group-focus-visible/stepper-trigger:ring-ring/50",
        className
      )}
      {...props}
    >
      <CheckIcon
        aria-hidden="true"
        weight="bold"
        className="hidden size-4 text-primary-foreground group-data-[state=complete]/stepper-trigger:block"
      />
      <span
        aria-hidden="true"
        className="hidden size-2.5 rounded-full bg-primary group-data-[state=active]/stepper-trigger:block"
      />
    </span>
  )
}

/** The line between two steps, filled once the step before it is done. */
function StepperSeparator({
  step,
  className,
  ...props
}: ComponentProps<"span"> & { step: number }) {
  const { activeStep } = useStepper()
  return (
    <span
      aria-hidden="true"
      data-slot="stepper-separator"
      data-complete={activeStep > step}
      className={cn(
        "h-0.5 flex-1 bg-border transition-all data-[complete=true]:bg-primary",
        className
      )}
      {...props}
    />
  )
}

/** "Step 2 of 7 — Identification". */
function StepperStatus({ className, children, ...props }: ComponentProps<"p">) {
  const { activeStep, stepCount } = useStepper()
  return (
    <p
      data-slot="stepper-status"
      className={cn("text-xs text-muted-foreground", className)}
      {...props}
    >
      Step {activeStep} of {stepCount}
      {children ? (
        <>
          {" — "}
          <span className="text-foreground">{children}</span>
        </>
      ) : null}
    </p>
  )
}

function StepperActiveStep() {
  return <>{useStepper().activeStep}</>
}

function StepperStepLength() {
  return <>{useStepper().stepCount}</>
}

export {
  Stepper,
  StepperActiveStep,
  StepperIndicator,
  StepperSeparator,
  StepperStatus,
  StepperStepLength,
  StepperTrigger,
  useStepper,
}
