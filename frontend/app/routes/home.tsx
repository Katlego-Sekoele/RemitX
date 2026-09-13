import { HowItWorks } from "~/components/landing/how-it-works"
import { LandingCta } from "~/components/landing/landing-cta"
import { LandingFooter } from "~/components/landing/landing-footer"
import { LandingHero } from "~/components/landing/landing-hero"
import { TrustNote } from "~/components/landing/trust-note"
import { VerificationCard } from "~/components/kyc/verification-card"

export default function Home() {
  return (
    <div className="flex w-full flex-col">
      <VerificationCard />
      <LandingHero />
      <HowItWorks />
      <TrustNote />
      <LandingCta />
      <LandingFooter />
    </div>
  )
}
