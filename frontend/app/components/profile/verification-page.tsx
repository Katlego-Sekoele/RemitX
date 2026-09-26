import { CaretRightIcon, PlusIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import {
  api,
  type KycApplicationSummaryRead,
  type KycStandingRead,
} from "~/client"
import { formatDate } from "~/components/admin/kyc-review/format"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import {
  SettingsAction,
  SettingsItem,
  SettingsItemDescription,
  SettingsPage,
  SettingsSection,
  SettingsSectionContent,
  SettingsSectionLabel,
  SettingsTitle,
} from "~/components/ui/settings"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import {
  applicationPath,
  canStartApplication,
  newApplicationPath,
  statusCopy,
  statusVariant,
} from "~/lib/kyc-onboarding"
import { formatMoney, isZeroMoney } from "~/lib/money"

/** KYC standing, its limits, and past applications. A custom page inside
 * Clerk's `<UserProfile>`; an application and its wizard open as pages. */
export function VerificationPage({ kyc }: { kyc: KycStandingRead }) {
  const history = useQuery(api.kyc.onboarding.listMyApplications())
  const copy = statusCopy(kyc.status)

  return (
    <SettingsPage>
      <SettingsTitle>Verification</SettingsTitle>
      <SettingsSection>
        <SettingsSectionLabel>Status</SettingsSectionLabel>
        <SettingsSectionContent>
          <SettingsItem>
            <Badge variant={statusVariant(kyc.status)}>{copy.title}</Badge>
            <SettingsItemDescription>{copy.body}</SettingsItemDescription>
          </SettingsItem>
        </SettingsSectionContent>
      </SettingsSection>
      <SettingsSection>
        <SettingsSectionLabel>Limits</SettingsSectionLabel>
        <SettingsSectionContent>
          <Allowance
            remaining={kyc.daily_remaining_zar}
            limit={kyc.daily_limit_zar}
            left="left today"
            per="per day"
          />
          <Allowance
            remaining={kyc.monthly_remaining_zar}
            limit={kyc.monthly_limit_zar}
            left="left this month"
            per="per month"
          />
        </SettingsSectionContent>
      </SettingsSection>
      <SettingsSection>
        <SettingsSectionLabel>Applications</SettingsSectionLabel>
        <SettingsSectionContent>
          {history.isPending ? (
            <Skeleton className="h-16 w-full" />
          ) : history.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(history.error)}</AlertDescription>
            </Alert>
          ) : (
            <Applications
              applications={history.data}
              canStart={canStartApplication(kyc.status)}
            />
          )}
        </SettingsSectionContent>
      </SettingsSection>
    </SettingsPage>
  )
}

/** "R 1,800.00 of R 3,000.00 left today": what's left after what was
 * already sent, as the API counts it when it checks a transfer. With no
 * allowance yet, just the limit. */
function Allowance({
  remaining,
  limit,
  left,
  per,
}: {
  remaining: string
  limit: string
  left: string
  per: string
}) {
  if (isZeroMoney(limit)) {
    return (
      <SettingsItem>
        {formatMoney(limit, "ZAR")}
        <SettingsItemDescription>{per}</SettingsItemDescription>
      </SettingsItem>
    )
  }
  return (
    <SettingsItem>
      {`${formatMoney(remaining, "ZAR")} of ${formatMoney(limit, "ZAR")}`}
      <SettingsItemDescription>{left}</SettingsItemDescription>
    </SettingsItem>
  )
}

function Applications({
  applications,
  canStart,
}: {
  applications: KycApplicationSummaryRead[]
  canStart: boolean
}) {
  const open = applications.find((application) => application.editable)

  return (
    <>
      {applications.map((application) => (
        <ApplicationItem
          key={application.application_id}
          application={application}
        />
      ))}
      {open ? (
        <SettingsAction
          nativeButton={false}
          render={<Link to={applicationPath(open.application_id)} />}
        >
          Continue verification
        </SettingsAction>
      ) : canStart ? (
        <SettingsAction
          nativeButton={false}
          render={<Link to={newApplicationPath()} />}
        >
          <PlusIcon data-icon="inline-start" />
          {applications.length === 0 ? "Start verification" : "New application"}
        </SettingsAction>
      ) : null}
    </>
  )
}

function ApplicationItem({
  application,
}: {
  application: KycApplicationSummaryRead
}) {
  const dates = [
    `Started ${formatDate(application.created_at)}`,
    application.submitted_at
      ? `submitted ${formatDate(application.submitted_at)}`
      : null,
    application.decided_at
      ? `decided ${formatDate(application.decided_at)}`
      : null,
  ].filter(Boolean)

  return (
    <SettingsItem
      render={<Link to={applicationPath(application.application_id)} />}
    >
      <Badge variant={statusVariant(application.status)}>
        {statusCopy(application.status).title}
      </Badge>
      <SettingsItemDescription>{dates.join(", ")}</SettingsItemDescription>
      <CaretRightIcon aria-hidden="true" className="ml-auto shrink-0" />
    </SettingsItem>
  )
}
