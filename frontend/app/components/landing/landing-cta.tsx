import { Link } from "react-router"

import { FadeIn } from "~/components/aceternity/fade-in"
import { Button } from "~/components/ui/button"

export function LandingCta() {
  return (
    <section className="border-t border-border px-6 py-20 lg:py-24">
      <FadeIn>
        <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-6 text-center">
          <h2 className="font-heading text-3xl font-semibold tracking-tight text-balance text-foreground md:text-4xl">
            Ready to send your first remittance?
          </h2>
          <p className="max-w-lg text-base text-muted-foreground md:text-lg">
            Create an account, run mock KYC, and move ZAR to RLUSD with fees you
            see before you confirm.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
            <Button
              size="lg"
              nativeButton={false}
              render={<Link to="/sign-up" />}
            >
              Create account
            </Button>
            <Button
              size="lg"
              variant="outline"
              nativeButton={false}
              render={<Link to="/sign-in" />}
            >
              Sign in
            </Button>
          </div>
        </div>
      </FadeIn>
    </section>
  )
}
