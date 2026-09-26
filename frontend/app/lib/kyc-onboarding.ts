/**
 * Verification URLs and status rules. Every link into verification is built
 * here, so moving the pages means changing this file and `routes.ts` only.
 */

import { KycStatus } from "~/client"

// Subset of `STARTABLE_STANDINGS` in api/remitx_api/models/orm/kyc_lifecycle.py.
// The server enforces it; this only decides whether to offer the button.
const STARTABLE_STANDING = new Set<KycStatus>([
  KycStatus.NOT_STARTED,
  KycStatus.REJECTED,
  KycStatus.REVIEW_DUE,
])

const OPEN_STATUSES = new Set<KycStatus>([
  KycStatus.IN_PROGRESS,
  KycStatus.SUBMITTED,
  KycStatus.UNDER_REVIEW,
  KycStatus.MORE_INFO_REQUIRED,
])

export function isKycVerified(
  standing: { is_verified?: boolean } | undefined
): boolean {
  return standing?.is_verified ?? false
}

export function canStartApplication(status: KycStatus | undefined): boolean {
  return status !== undefined && STARTABLE_STANDING.has(status)
}

export function isOpenStatus(status: KycStatus | undefined): boolean {
  return status !== undefined && OPEN_STATUSES.has(status)
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

export const KYC_STATUS_COPY: Record<
  KycStatus,
  { title: string; body: string }
> = {
  [KycStatus.NOT_STARTED]: {
    title: "Not started",
    body: "Verify your identity to start sending.",
  },
  [KycStatus.IN_PROGRESS]: {
    title: "In progress",
    body: "Your draft is saved.",
  },
  [KycStatus.SUBMITTED]: {
    title: "Submitted",
    body: "We're reviewing your application.",
  },
  [KycStatus.UNDER_REVIEW]: {
    title: "Under review",
    body: "A reviewer is looking at your application.",
  },
  [KycStatus.MORE_INFO_REQUIRED]: {
    title: "More information needed",
    body: "Update your application and submit again.",
  },
  [KycStatus.APPROVED]: {
    title: "Approved",
    body: "You're verified and can start sending.",
  },
  [KycStatus.REJECTED]: {
    title: "Not approved",
    body: "You can start a new application.",
  },
  [KycStatus.REVIEW_DUE]: {
    title: "Review due",
    body: "Your verification has expired. Start a new application to renew it.",
  },
}

export function statusCopy(status: KycStatus | undefined) {
  return KYC_STATUS_COPY[status ?? KycStatus.NOT_STARTED]
}

export function statusVariant(
  status: KycStatus | undefined
): "default" | "destructive" | "outline" | "secondary" {
  switch (status) {
    case KycStatus.APPROVED:
      return "default"
    case KycStatus.REJECTED:
    case KycStatus.MORE_INFO_REQUIRED:
    case KycStatus.REVIEW_DUE:
      return "destructive"
    case KycStatus.IN_PROGRESS:
      return "outline"
    default:
      return "secondary"
  }
}
