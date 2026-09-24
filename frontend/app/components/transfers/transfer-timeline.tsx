import type { TransferRead as Transfer } from "~/client"
import {
  Timeline,
  TimelineContent,
  TimelineDate,
  TimelineHeader,
  TimelineIndicator,
  TimelineItem,
  TimelineSeparator,
  TimelineTitle,
} from "~/components/reui/timeline"
import { formatWhen } from "~/lib/transfers"

/** Quote accepted, Queued, Settling on XRPL Testnet, then Completed or
 * Failed. */
export function TransferTimeline({ transfer }: { transfer: Transfer }) {
  return (
    <Timeline value={transfer.timeline_step}>
      {transfer.timeline.map((stage) => (
        <TimelineItem key={stage.step} step={stage.step}>
          <TimelineHeader>
            <TimelineSeparator />
            {stage.occurred_at ? (
              <TimelineDate dateTime={stage.occurred_at}>
                {formatWhen(stage.occurred_at)}
              </TimelineDate>
            ) : null}
            <TimelineTitle>{stage.title}</TimelineTitle>
            <TimelineIndicator />
          </TimelineHeader>
          <TimelineContent>{stage.description}</TimelineContent>
        </TimelineItem>
      ))}
    </Timeline>
  )
}
