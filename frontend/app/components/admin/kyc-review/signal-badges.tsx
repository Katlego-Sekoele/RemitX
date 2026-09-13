import { humanise } from "~/components/admin/kyc-review/format"
import { Badge } from "~/components/ui/badge"
import type { KycMatchedSignalRead, KycRiskSignalRead } from "~/client"

/** The signals that scored an assessment, labelled from the rule set so a
 * renamed signal needs no frontend change. */
export function SignalBadges({
  matched,
  signals,
}: {
  matched: readonly KycMatchedSignalRead[]
  signals: readonly KycRiskSignalRead[]
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {matched.map((row) => {
        const rule = signals.find((signal) => signal.signal === row.signal)
        return (
          <Badge key={row.signal} variant="secondary" title={rule?.description}>
            <span className="first-letter:uppercase">
              {humanise(row.signal)}
            </span>
            <span className="tabular-nums">
              {row.score_effect > 0 ? `+${row.score_effect}` : row.score_effect}
            </span>
          </Badge>
        )
      })}
    </div>
  )
}
