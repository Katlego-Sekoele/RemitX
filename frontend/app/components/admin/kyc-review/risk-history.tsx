import { WarningIcon } from "@phosphor-icons/react"

import {
  errorMessage,
  formatDateTime,
  humanise,
} from "~/components/admin/kyc-review/format"
import { SignalBadges } from "~/components/admin/kyc-review/signal-badges"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"
import { Skeleton } from "~/components/ui/skeleton"
import type { KycAssessmentAuditRead, KycRiskSignalRead } from "~/client"

/** Every rating and tier change, newest first. */
export function RiskHistory({
  entries,
  loading,
  error,
  signals,
}: {
  entries: readonly KycAssessmentAuditRead[] | undefined
  loading: boolean
  error: unknown
  signals: readonly KycRiskSignalRead[]
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk history</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-20 w-full" />
        ) : error ? (
          <Alert variant="destructive">
            <WarningIcon />
            <AlertTitle>Could not load risk history</AlertTitle>
            <AlertDescription>{errorMessage(error)}</AlertDescription>
          </Alert>
        ) : !entries || entries.length === 0 ? (
          <p className="text-muted-foreground">Not scored yet.</p>
        ) : (
          <ItemGroup>
            {[...entries].reverse().map((entry) => (
              <HistoryEntry
                key={entry.audit_id}
                entry={entry}
                signals={signals}
              />
            ))}
          </ItemGroup>
        )}
      </CardContent>
    </Card>
  )
}

function HistoryEntry({
  entry,
  signals,
}: {
  entry: KycAssessmentAuditRead
  signals: readonly KycRiskSignalRead[]
}) {
  const overridden =
    entry.final_risk_rating != null &&
    entry.final_risk_rating !== entry.computed_risk_rating

  return (
    <Item variant="outline" size="sm">
      <ItemContent>
        <ItemTitle className="capitalize">
          {humanise(entry.final_risk_rating ?? entry.computed_risk_rating)} risk
          {entry.risk_score != null ? ` · score ${entry.risk_score}` : ""}
          {entry.final_tier != null ? ` · tier ${entry.final_tier}` : ""}
          {overridden ? <Badge variant="outline">Overridden</Badge> : null}
        </ItemTitle>
        <ItemDescription>
          {formatDateTime(entry.recorded_at)}
          {overridden
            ? ` · computed ${humanise(entry.computed_risk_rating)}`
            : ""}
          {entry.reason ? ` · ${entry.reason}` : ""}
        </ItemDescription>
        {entry.matched_signals.length > 0 ? (
          <SignalBadges matched={entry.matched_signals} signals={signals} />
        ) : null}
      </ItemContent>
    </Item>
  )
}
