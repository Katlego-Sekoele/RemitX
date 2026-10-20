import { ScrollIcon } from "@phosphor-icons/react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { api, type AuditLogRead } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { formatDateTime } from "~/components/admin/kyc-review/format"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { Field, FieldLabel } from "~/components/ui/field"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { Skeleton } from "~/components/ui/skeleton"
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
  AUDIT_AREAS,
  auditTxHash,
  isStokvelEntry,
  STOKVEL_AUDIT_ACTIONS,
} from "~/lib/audit-entry"
import { PERMISSIONS } from "~/lib/permissions"
import { explorerTxUrl } from "~/lib/stokvels"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/audit"

const ROUTE_MODULE = "routes/admin/audit.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

const ALL_ACTIONS = "__all__"

const ACTION_OPTIONS = [
  { value: ALL_ACTIONS, label: "All actions" },
  { value: "audit.log.viewed", label: "Audit log viewed" },
  { value: "kyc.pii.viewed", label: "KYC PII viewed" },
  { value: "kyc.document.viewed", label: "KYC document viewed" },
  { value: "kyc.application.decided", label: "KYC application decided" },
  { value: "cashin.confirmed", label: "Cash-in confirmed" },
  { value: "cashout.bank_account.verified", label: "Bank account verified" },
  { value: "cashout.bank_account.rejected", label: "Bank account rejected" },
  { value: "role.granted", label: "Role granted" },
  { value: "role.revoked", label: "Role revoked" },
  ...STOKVEL_AUDIT_ACTIONS,
] as const

const ALL_AREAS = "__all__"

const AREA_OPTIONS = [
  { value: ALL_AREAS, label: "All areas" },
  ...AUDIT_AREAS,
] as const

const PAGE_SIZE = 50

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

export default function AuditLogPage() {
  const canRead = useHasPermission(PERMISSIONS.auditRead)
  if (!canRead) return <ForbiddenPage />
  return <AuditLogPageContent />
}

function actionBadgeVariant(
  action: string
): "default" | "secondary" | "destructive" {
  if (
    action === "kyc.pii.viewed" ||
    action === "kyc.document.viewed" ||
    action === "stokvel.contract.paused" ||
    action === "stokvel.round.finalised_manually"
  ) {
    return "destructive"
  }
  if (action === "role.granted" || action === "audit.log.viewed") {
    return "secondary"
  }
  return "default"
}

function isSelfGrant(entry: AuditLogRead): boolean {
  return (
    entry.action === "role.granted" &&
    entry.after != null &&
    typeof entry.after === "object" &&
    "self_granted" in entry.after &&
    entry.after.self_granted === true
  )
}

/** The list filters as `GET /admin/audit` query params. */
function filterParams(actionFilter: string, areaFilter: string) {
  return {
    ...(actionFilter !== ALL_ACTIONS ? { action: actionFilter } : {}),
    ...(areaFilter !== ALL_AREAS ? { subject_type: areaFilter } : {}),
  }
}

function listQueryOptions(actionFilter: string, areaFilter: string) {
  return api.admin.audit.listAuditLog({
    query: { limit: PAGE_SIZE, ...filterParams(actionFilter, areaFilter) },
  })
}

function AuditLogPageContent() {
  const queryClient = useQueryClient()
  const [actionFilter, setActionFilter] = useState(ALL_ACTIONS)
  const [areaFilter, setAreaFilter] = useState(ALL_AREAS)
  const [rows, setRows] = useState<AuditLogRead[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const query = useQuery(listQueryOptions(actionFilter, areaFilter))

  useEffect(() => {
    if (query.data === undefined) return
    setRows(query.data)
    setHasMore(query.data.length >= PAGE_SIZE)
  }, [query.data])

  // The effect above repopulates the rows when the query key changes. Don't
  // clear them here: with both filters already at All the key doesn't change,
  // and the table would stay empty until a refetch.
  const resetFilters = () => {
    setActionFilter(ALL_ACTIONS)
    setAreaFilter(ALL_AREAS)
  }

  const loadOlder = async () => {
    const last = rows.at(-1)
    if (!last || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await queryClient.fetchQuery(
        api.admin.audit.listAuditLog({
          query: {
            limit: PAGE_SIZE,
            before: last.created_at,
            ...filterParams(actionFilter, areaFilter),
          },
        })
      )
      setRows((prev) => [...prev, ...page])
      setHasMore(page.length >= PAGE_SIZE)
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle className="flex items-center gap-2">
            <ScrollIcon aria-hidden />
            {pageRoutingContext?.title}
          </PageHeaderTitle>
          <PageHeaderDescription>
            Privileged actions and sensitive reads, newest first. Opening this
            page is recorded too.
          </PageHeaderDescription>
        </PageHeader>

        <Card>
          <CardHeader>
            <CardTitle>Filters</CardTitle>
            <CardDescription>
              Narrow by action or area; "Stokvels" and "Stokvel contract" show
              the stokvel admin actions. Each refresh or page load writes an
              audit entry.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <Field className="min-w-[220px] flex-1">
              <FieldLabel>Action</FieldLabel>
              <Select
                value={actionFilter}
                onValueChange={(value) => {
                  setActionFilter(value ?? ALL_ACTIONS)
                  setRows([])
                  setHasMore(false)
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All actions" />
                </SelectTrigger>
                <SelectContent>
                  {ACTION_OPTIONS.map((option) => (
                    <SelectItem key={option.label} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field className="min-w-[180px]">
              <FieldLabel>Area</FieldLabel>
              <Select
                value={areaFilter}
                onValueChange={(value) => {
                  setAreaFilter(value ?? ALL_AREAS)
                  setRows([])
                  setHasMore(false)
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All areas" />
                </SelectTrigger>
                <SelectContent>
                  {AREA_OPTIONS.map((option) => (
                    <SelectItem key={option.label} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Button type="button" variant="outline" onClick={resetFilters}>
              Reset
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Entries</CardTitle>
          </CardHeader>
          <CardContent>
            {query.isPending && rows.length === 0 ? (
              <Skeleton className="h-48 w-full" />
            ) : query.isError ? (
              <QueryError
                title="Could not load audit log"
                error={query.error}
                onRetry={() => query.refetch()}
              />
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>When</TableHead>
                      <TableHead>Actor</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead>Subject</TableHead>
                      <TableHead>Detail</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={5}
                          className="text-muted-foreground"
                        >
                          No entries match these filters.
                        </TableCell>
                      </TableRow>
                    ) : (
                      rows.map((entry) => (
                        <TableRow key={entry.audit_id}>
                          <TableCell className="text-sm whitespace-nowrap">
                            {formatDateTime(entry.created_at)}
                          </TableCell>
                          <TableCell className="max-w-[180px] truncate text-sm">
                            {entry.actor_email}
                          </TableCell>
                          <TableCell>
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant={actionBadgeVariant(entry.action)}>
                                {entry.action}
                              </Badge>
                              {isSelfGrant(entry) ? (
                                <Badge variant="outline">Self-grant</Badge>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {entry.subject_type}
                            <br />
                            {entry.subject_id}
                          </TableCell>
                          <TableCell className="max-w-md text-xs text-muted-foreground">
                            <AuditDetail entry={entry} />
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
                {hasMore ? (
                  <div className="mt-4 flex justify-center">
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={loadingMore}
                      onClick={loadOlder}
                    >
                      {loadingMore ? "Loading…" : "Load older entries"}
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </AdminPageFrame>
  )
}

/**
 * The reason, or the recorded change. Stokvel entries (#261) also link their
 * on-chain transaction to the explorer, so staff can check what happened.
 */
function AuditDetail({ entry }: { entry: AuditLogRead }) {
  const hash = isStokvelEntry(entry) ? auditTxHash(entry) : null
  return (
    <div className="flex flex-col gap-1">
      <span className="truncate">
        {entry.reason ?? JSON.stringify(entry.after ?? entry.before ?? {})}
      </span>
      {hash ? (
        <a
          href={explorerTxUrl(hash)}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono underline"
          title={hash}
        >
          {hash.slice(0, 6)}…{hash.slice(-4)}
        </a>
      ) : null}
    </div>
  )
}
