import { redirect } from "react-router"

import { verificationPath } from "~/lib/kyc-onboarding"

// Verification used to live at /onboarding/* and then /app/verification/*,
// addressed by step with no application id. A step link cannot be mapped to an
// application, so every old link lands on the history page, which offers
// Continue or Start as the account allows.
export async function clientLoader() {
  throw redirect(verificationPath())
}

export default function LegacyVerificationRedirect() {
  return null
}
