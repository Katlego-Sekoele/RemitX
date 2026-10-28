import { LandingCta } from "~/components/landing/landing-cta"
import { LandingFooter } from "~/components/landing/landing-footer"
import { LandingHero } from "~/components/landing/landing-hero"
import { LandingParallax } from "~/components/landing/landing-parallax"
import { LandingPaths } from "~/components/landing/landing-paths"
import { TrustNote } from "~/components/landing/trust-note"
import { VerificationCard } from "~/components/kyc/verification-card"

export default function Home() {
  return (
    <div className="flex w-full flex-col overflow-x-clip">
      <VerificationCard />
      <LandingHero />
      <LandingParallax />
      <LandingPaths />
      <TrustNote />
      <LandingCta />
      <LandingFooter />
    </div>
  )
}
