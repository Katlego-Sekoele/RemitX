import { CaretDownIcon, WarningIcon } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router"

import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import {
  errorMessage,
  formatDate,
  humanise,
  ratingVariant,
  reviewHref,
} from "~/components/admin/kyc-review/format"
import { SelfDeclaredNotice } from "~/components/kyc/self-declared-notice"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"
import { Skeleton } from "~/components/ui/skeleton"
import { useKycReferenceQuery } from "~/hooks/use-kyc-reference"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { useHasPermission } from "~/hooks/use-permissions"
import {
  api,
  type KycApplicationRead as KycApplication,
  type KycRiskRatingRead as KycRiskRating,
} from "~/client"
import { PERMISSIONS } from "~/lib/permissions"
import { countryName } from "~/lib/kyc-reference"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/applications"

// The literal path, not `import.meta.filename` — see routes/admin/access.tsx.
const ROUTE_MODULE = "routes/admin/kyc/applications.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

const ALL_RATINGS = "all"
const ALL_STATUSES = "all"

/**
 * Mirrors how the API gates this page (api/remitx_api/routes/admin/kyc.py):
 * reading the queue needs `kyc:application:read`. Overriding a rating happens
 * on the review page, beside the evidence that justifies it. The server
 * decides; this only keeps the UI from offering what it would refuse.
 */
export default function KycApplications() {
  const canRead = useHasPermission(PERMISSIONS.kycApplicationRead)

  if (!canRead) return <ForbiddenPage />

  return <KycApplicationsPage />
}

function KycApplicationsPage() {
  const [rating, setRating] = useState(ALL_RATINGS)
  const [status, setStatus] = useState(ALL_STATUSES)

  const rules = useQuery(api.admin.kyc.applications.getRiskRules())
  const applications = useQuery(
    api.admin.kyc.applications.listApplications({
      query: {
        ...(rating === ALL_RATINGS ? {} : { risk_rating: rating }),
        ...(status === ALL_STATUSES
          ? {}
          : { status: [status as "submitted" | "under_review"] }),
      },
    })
  )

  const ratings = rules.data?.ratings ?? []

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          {pageRoutingContext?.title}
        </h1>
        <p className="max-w-xl text-sm text-muted-foreground">
          Highest risk first.
        </p>
      </div>

      <SelfDeclaredNotice audience="reviewer" />

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4">
          <CardTitle>Review queue</CardTitle>
          <div className="flex flex-wrap gap-2">
            <StatusFilter value={status} onChange={setStatus} />
            <RatingFilter
              ratings={ratings}
              value={rating}
              onChange={setRating}
            />
          </div>
        </CardHeader>
        <CardContent>
          <QueueTable
            applications={applications.data}
            loading={applications.isPending}
            error={applications.isError ? applications.error : null}
            ratings={ratings}
          />
        </CardContent>
      </Card>
    </AdminPageFrame>
  )
}

function StatusFilter({
  value,
  onChange,
}: {
  value: string
  onChange: (next: string) => void
}) {
  const options = [
    [ALL_STATUSES, "All waiting"],
    ["submitted", "Submitted"],
    ["under_review", "Under review"],
  ] as const

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline" className="justify-between" />}
      >
        {options.find(([id]) => id === value)?.[1] ?? "Status"}
        <CaretDownIcon data-icon="inline-end" />
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuRadioGroup
          value={value}
          onValueChange={(next) => onChange(String(next))}
        >
          {options.map(([id, label]) => (
            <DropdownMenuRadioItem key={id} value={id}>
              {label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function RatingFilter({
  ratings,
  value,
  onChange,
}: {
  ratings: readonly KycRiskRating[]
  value: string
  onChange: (next: string) => void
}) {
  const bySeverity = [...ratings].sort((a, b) => b.severity - a.severity)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline" className="justify-between" />}
      >
        {value === ALL_RATINGS ? "All ratings" : `${humanise(value)} risk`}
        <CaretDownIcon data-icon="inline-end" />
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuRadioGroup
          value={value}
          onValueChange={(next) => onChange(String(next))}
        >
          <DropdownMenuRadioItem value={ALL_RATINGS}>
            All ratings
          </DropdownMenuRadioItem>
          {bySeverity.map((row) => (
            <DropdownMenuRadioItem key={row.rating} value={row.rating}>
              {humanise(row.rating)} risk
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function QueueTable({
  applications,
  loading,
  error,
  ratings,
}: {
  applications: KycApplication[] | undefined
  loading: boolean
  error: unknown
  ratings: readonly KycRiskRating[]
}) {
  const { data: reference } = useKycReferenceQuery()
  const navigate = useNavigate()

  if (loading) return <Skeleton className="h-24 w-full" />

  if (error) {
    return (
      <Alert variant="destructive">
        <WarningIcon />
        <AlertTitle>Could not load the queue</AlertTitle>
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    )
  }

  if (!applications || applications.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing is waiting on a reviewer at this rating.
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Applicant</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Submitted</TableHead>
          <TableHead>Score</TableHead>
          <TableHead>Rating</TableHead>
          <TableHead>PEP</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {applications.map((application) => (
          <TableRow
            key={application.application_id}
            aria-label={`Review application for ${application.full_name ?? "applicant"}`}
            className="cursor-pointer"
            tabIndex={0}
            onClick={() => navigate(reviewHref(application.application_id))}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault()
                navigate(reviewHref(application.application_id))
              }
            }}
          >
            <TableCell>
              <div className="flex flex-col">
                <span>{application.full_name ?? "—"}</span>
                <span className="text-[11px] text-muted-foreground">
                  {countryName(reference, application.nationality)} national,
                  lives in{" "}
                  {countryName(reference, application.residential_country)}
                </span>
              </div>
            </TableCell>
            <TableCell className="capitalize">
              {humanise(application.status)}
            </TableCell>
            <TableCell>{formatDate(application.submitted_at)}</TableCell>
            <TableCell className="tabular-nums">
              {application.risk_score ?? "—"}
            </TableCell>
            <TableCell>
              <div className="flex flex-col items-start gap-1">
                <Badge
                  variant={ratingVariant(
                    application.effective_risk_rating,
                    ratings
                  )}
                  className="capitalize"
                >
                  {humanise(application.effective_risk_rating)}
                </Badge>
                {application.risk_rating_override && (
                  <span
                    className="text-[11px] text-muted-foreground"
                    title={application.risk_rating_override_reason ?? undefined}
                  >
                    Overridden — computed {humanise(application.risk_rating)}
                  </span>
                )}
              </div>
            </TableCell>
            <TableCell>
              {application.declares_pep ? (
                <Badge variant="destructive">
                  {humanise(application.pep_relationship)}
                </Badge>
              ) : (
                <span className="text-muted-foreground">No</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
