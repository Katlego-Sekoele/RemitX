export const KYC_ONBOARDING_KEY = ["kyc", "onboarding"] as const

const VERIFIED_STANDING = new Set(["approved", "review_due"])

export function isKycVerified(status: string | undefined): boolean {
  return VERIFIED_STANDING.has(status ?? "")
}

export function pathForStep(step: string): string {
  if (step === "welcome") return "/app/verification"
  return `/app/verification/${step}`
}
