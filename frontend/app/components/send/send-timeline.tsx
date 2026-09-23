import { CheckIcon } from "@phosphor-icons/react"
import type { ReactNode } from "react"

import {
  Timeline,
  TimelineContent,
  TimelineHeader,
  TimelineIndicator,
  TimelineItem,
  TimelineSeparator,
  TimelineTitle,
} from "~/components/reui/timeline"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "~/components/ui/accordion"
import { SEND_STEPS, stepNumber, type SendPageStep } from "~/lib/send"

export type SendSection = {
  step: SendPageStep
  /** Shown under the title once the section is done, e.g. who and how much. */
  summary?: ReactNode
  /** Can't be opened until the sections before it are filled in. */
  disabled: boolean
  /** Rendered only while the section is open. */
  content: ReactNode
}

/**
 * The send flow as one page: each section is an accordion item on a vertical
 * timeline, open one at a time. Sections already done read as a summary, so
 * the sender sees what they chose without paging back. Sent is the last
 * point on the line, not a section: a confirmed transfer lands on its own
 * page (SEND-3).
 */
export function SendTimeline({
  step,
  sections,
  onStepChange,
}: {
  step: SendPageStep
  sections: SendSection[]
  onStepChange: (step: SendPageStep) => void
}) {
  const sent = SEND_STEPS[SEND_STEPS.length - 1]

  return (
    <Timeline value={stepNumber(step)}>
      <Accordion
        value={[step]}
        onValueChange={(value) => {
          // One section is always open: closing the open one does nothing.
          const next = value[0] as SendPageStep | undefined
          if (next && next !== step) onStepChange(next)
        }}
      >
        {sections.map((section) => {
          const open = section.step === step
          const done = stepNumber(section.step) < stepNumber(step)
          const title = SEND_STEPS[stepNumber(section.step) - 1].title
          return (
            <TimelineItem
              key={section.step}
              step={stepNumber(section.step)}
              render={
                <AccordionItem
                  value={section.step}
                  disabled={section.disabled}
                />
              }
            >
              <TimelineHeader>
                <TimelineSeparator />
                <TimelineIndicator
                  data-done={done || undefined}
                  className="flex items-center justify-center data-done:bg-primary"
                >
                  {done ? (
                    <CheckIcon
                      weight="bold"
                      className="size-2.5 text-primary-foreground"
                    />
                  ) : null}
                </TimelineIndicator>
                <AccordionTrigger>
                  <span className="flex min-w-0 flex-col gap-1">
                    <TimelineTitle render={<span />}>{title}</TimelineTitle>
                    {!open && section.summary ? (
                      <TimelineContent render={<span />}>
                        {section.summary}
                      </TimelineContent>
                    ) : null}
                  </span>
                </AccordionTrigger>
              </TimelineHeader>
              <AccordionContent>
                {open ? section.content : null}
              </AccordionContent>
            </TimelineItem>
          )
        })}
        <TimelineItem step={stepNumber(sent.key)}>
          <TimelineHeader>
            <TimelineSeparator />
            <TimelineIndicator />
            <TimelineTitle>{sent.title}</TimelineTitle>
            <TimelineContent>
              Once you confirm, you can follow it until it lands.
            </TimelineContent>
          </TimelineHeader>
        </TimelineItem>
      </Accordion>
    </Timeline>
  )
}
