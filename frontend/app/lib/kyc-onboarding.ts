/**
 * Verification URLs and status rules. Every link into verification is built
 * here, so moving the pages means changing this file and `routes.ts` only.
 */

const VERIFIED_STANDING = new Set(["approved", "review_due"])

// Mirrors STARTABLE_STANDINGS in api/remitx_api/models/orm/kyc_lifecycle.py.
// The server enforces it; this only decides whether to offer the button.
const STARTABLE_STANDING = new Set(["not_started", "rejected", "review_due"])

const OPEN_STATUSES = new Set([
  "in_progress",
  "submitted",
  "under_review",
  "more_info_required",
])

export function isKycVerified(status: string | undefined): boolean {
  return VERIFIED_STANDING.has(status ?? "")
}

export function canStartApplication(status: string | undefined): boolean {
  return STARTABLE_STANDING.has(status ?? "")
}

export function isOpenStatus(status: string | undefined): boolean {
  return OPEN_STATUSES.has(status ?? "")
}

/** Standing and history: the Verification page of Clerk's <UserProfile>. An
 * application and its wizard are routes of their own beneath it. */
export function verificationPath(): string {
  return "/app/profile/verification"
}

export function newApplicationPath(): string {
  return `${verificationPath()}/new`
}

export function applicationPath(applicationId: string): string {
  return `${verificationPath()}/${applicationId}`
}

/** A wizard step of one application. The catalogue's entry step belongs to
 * starting a new application, and its outcome step is the detail page. */
export function applicationStepPath(
  applicationId: string,
  step: string
): string {
  if (step === "welcome") return newApplicationPath()
  if (step === "status") return applicationPath(applicationId)
  return `${applicationPath(applicationId)}/${step}`
}

export const KYC_STATUS_COPY: Record<string, { title: string; body: string }> =
  {
    not_started: {
      title: "Not started",
      body: "Verify your identity to start sending.",
    },
    in_progress: { title: "In progress", body: "Your draft is saved." },
    submitted: {
      title: "Submitted",
      body: "We're reviewing your application.",
    },
    under_review: {
      title: "Under review",
      body: "A reviewer is looking at your application.",
    },
    more_info_required: {
      title: "More information needed",
      body: "Update your application and submit again.",
    },
    approved: {
      title: "Approved",
      body: "You're verified and can start sending.",
    },
    rejected: {
      title: "Not approved",
      body: "You can start a new application.",
    },
    review_due: {
      title: "Review due",
      body: "Your verification has expired. Start a new application to renew it.",
    },
  }

export function statusCopy(status: string | undefined) {
  return KYC_STATUS_COPY[status ?? ""] ?? KYC_STATUS_COPY.not_started
}

export function statusVariant(
  status: string | undefined
): "default" | "destructive" | "outline" | "secondary" {
  switch (status) {
    case "approved":
      return "default"
    case "rejected":
    case "more_info_required":
    case "review_due":
      return "destructive"
    case "in_progress":
      return "outline"
    default:
      return "secondary"
  }
}
