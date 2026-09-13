import {
  CaretDownIcon,
  PencilSimpleIcon,
  WarningIcon,
} from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { KycApplicationDocuments } from "~/components/admin/kyc-application-documents"
import { SelfDeclaredNotice } from "~/components/kyc/self-declared-notice"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"
import { Input } from "~/components/ui/input"
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

// A rating may only be overridden while a decision is pending — the server
// refuses anything else (repositories/kyc_application_repository.py).
const OVERRIDABLE_STATUSES = new Set(["submitted", "under_review"])

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}

function formatDate(value: string | null) {
  if (!value) return "—"
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

function humanise(value: string | null) {
  return value ? value.replaceAll("_", " ") : "—"
}

/**
 * A rating's badge, chosen by its `severity` relative to the other ratings
 * rather than by its name — the ratings are rows, and a renamed or added one
 * must not need a frontend change to look right.
 */
function ratingVariant(
  rating: string | null,
  ratings: readonly KycRiskRating[]
): "destructive" | "outline" | "secondary" {
  const match = ratings.find((row) => row.rating === rating)
  if (!match || ratings.length === 0) return "outline"
  const severities = ratings.map((row) => row.severity)
  if (match.severity === Math.max(...severities)) return "destructive"
  if (match.severity === Math.min(...severities)) return "secondary"
  return "outline"
}

/**
 * Mirrors how the API gates this page (api/remitx_api/routes/admin/kyc.py):
 * reading the queue needs `kyc:application:read`, and overriding a rating
 * needs `kyc:risk:write` on top. The server decides; this only keeps the UI
 * from offering what it would refuse.
 */
export default function KycApplications() {
  const canRead = useHasPermission(PERMISSIONS.kycApplicationRead)

  if (!canRead) return <ForbiddenPage />

  return <KycApplicationsPage />
}

function KycApplicationsPage() {
  const [rating, setRating] = useState(ALL_RATINGS)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const rules = useQuery(api.admin.kyc.applications.getRiskRules())
  const applications = useQuery(
    api.admin.kyc.applications.listApplications({
      query: rating === ALL_RATINGS ? {} : { risk_rating: rating },
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
          <RatingFilter ratings={ratings} value={rating} onChange={setRating} />
        </CardHeader>
        <CardContent>
          <QueueTable
            applications={applications.data}
            loading={applications.isPending}
            error={applications.isError ? applications.error : null}
            ratings={ratings}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </CardContent>
      </Card>

      {selectedId ? (
        <KycApplicationDocuments applicationId={selectedId} />
      ) : null}
    </AdminPageFrame>
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
  selectedId,
  onSelect,
}: {
  applications: KycApplication[] | undefined
  loading: boolean
  error: unknown
  ratings: readonly KycRiskRating[]
  selectedId: string | null
  onSelect: (applicationId: string) => void
}) {
  const { data: reference } = useKycReferenceQuery()
  const canOverride = useHasPermission(PERMISSIONS.kycRiskWrite)

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
          <TableHead className="w-8" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {applications.map((application) => (
          <TableRow
            key={application.application_id}
            data-state={
              selectedId === application.application_id ? "selected" : undefined
            }
            aria-selected={selectedId === application.application_id}
            aria-label={`View documents for ${application.full_name ?? "applicant"}`}
            className="cursor-pointer"
            tabIndex={0}
            onClick={() => onSelect(application.application_id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault()
                onSelect(application.application_id)
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
            <TableCell
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => event.stopPropagation()}
            >
              {canOverride && OVERRIDABLE_STATUSES.has(application.status) && (
                <OverrideDialog application={application} ratings={ratings} />
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** A reviewer's rating, set beside the computed one — never over it. */
function OverrideDialog({
  application,
  ratings,
}: {
  application: KycApplication
  ratings: readonly KycRiskRating[]
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [rating, setRating] = useState("")
  const [reason, setReason] = useState("")

  const override = useMutation({
    ...api.admin.kyc.applications.overrideRiskRating(),
    onSuccess: () => {
      // Keys match partially, so this refreshes every rating filter's queue.
      queryClient.invalidateQueries({
        queryKey: api.admin.kyc.applications.listApplications().queryKey,
      })
      setOpen(false)
    },
  })

  const canSubmit = rating !== "" && reason.trim() !== "" && !override.isPending

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setRating("")
          setReason("")
          override.reset()
        }
      }}
    >
      <DialogTrigger render={<Button variant="ghost" size="icon-sm" />}>
        <PencilSimpleIcon />
        <span className="sr-only">Override risk rating</span>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Override risk rating</DialogTitle>
          <DialogDescription>
            Computed: {humanise(application.risk_rating)} (score{" "}
            {application.risk_score ?? "—"})
          </DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (canSubmit) {
              override.mutate({
                path: { application_id: application.application_id },
                body: {
                  rating,
                  reason: reason.trim(),
                  expected_version: application.version,
                },
              })
            }
          }}
        >
          <DropdownMenu>
            <DropdownMenuTrigger
              render={<Button variant="outline" className="justify-between" />}
            >
              {rating ? `${humanise(rating)} risk` : "Select a rating"}
              <CaretDownIcon data-icon="inline-end" />
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuRadioGroup
                value={rating}
                onValueChange={(next) => setRating(String(next))}
              >
                {[...ratings]
                  .sort((a, b) => b.severity - a.severity)
                  .map((row) => (
                    <DropdownMenuRadioItem key={row.rating} value={row.rating}>
                      <span className="flex flex-col gap-0.5 py-0.5">
                        <span className="font-medium capitalize">
                          {humanise(row.rating)}
                        </span>
                        <span className="text-[11px] text-muted-foreground">
                          {row.description}
                        </span>
                      </span>
                    </DropdownMenuRadioItem>
                  ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" htmlFor="override-reason">
              Reason
            </label>
            <Input
              id="override-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Why the computed rating is wrong"
              disabled={override.isPending}
            />
          </div>

          {override.isError && (
            <Alert variant="destructive">
              <WarningIcon />
              <AlertTitle>Could not override</AlertTitle>
              <AlertDescription>
                {errorMessage(override.error)}
              </AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button type="submit" disabled={!canSubmit}>
              {override.isPending ? "Saving…" : "Override rating"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
