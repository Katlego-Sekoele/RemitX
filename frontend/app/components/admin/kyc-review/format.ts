import type { QueryClient } from "@tanstack/react-query"

import { api, type KycRiskRatingRead } from "~/client"

export const QUEUE_HREF = "/admin/kyc/applications"

export function reviewHref(applicationId: string) {
  return `${QUEUE_HREF}/${applicationId}`
}

// A rating may only be overridden, and a decision made, while one is pending —
// the server refuses anything else (repositories/kyc_application_repository.py).
export const PENDING_STATUSES = new Set(["submitted", "under_review"])

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}

export function humanise(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "—"
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "—"
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "—"
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

export function formatZar(value: string | null | undefined) {
  if (value == null || value === "") return "—"
  return new Intl.NumberFormat("en-ZA", {
    style: "currency",
    currency: "ZAR",
    maximumFractionDigits: 0,
  }).format(Number(value))
}

/**
 * A rating's badge, chosen by its `severity` relative to the other ratings
 * rather than by its name — the ratings are rows, and a renamed or added one
 * must not need a frontend change to look right.
 */
export function ratingVariant(
  rating: string | null | undefined,
  ratings: readonly KycRiskRatingRead[]
): "destructive" | "outline" | "secondary" {
  const match = ratings.find((row) => row.rating === rating)
  if (!match || ratings.length === 0) return "outline"
  const severities = ratings.map((row) => row.severity)
  if (match.severity === Math.max(...severities)) return "destructive"
  if (match.severity === Math.min(...severities)) return "secondary"
  return "outline"
}

/** Refresh everything that shows this application: the queue, its count, the
 * review itself and its risk history. */
export function invalidateApplication(
  queryClient: QueryClient,
  applicationId: string
) {
  const path = { path: { application_id: applicationId } }
  for (const queryKey of [
    api.admin.kyc.applications.listApplications().queryKey,
    api.admin.kyc.applications.getQueueCount().queryKey,
    api.admin.kyc.applications.getReviewApplication(path).queryKey,
    api.admin.kyc.applications.listAssessmentAudit(path).queryKey,
  ]) {
    queryClient.invalidateQueries({ queryKey })
  }
}
