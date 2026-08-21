import { Link } from "react-router"

import { FadeIn } from "~/components/aceternity/fade-in"
import { LazyGlobeDemo } from "~/components/aceternity/lazy-globe-demo"
import { RemitXLogo } from "~/components/remitx-logo"
import { Button } from "~/components/ui/button"
import { SITE_NAME } from "~/lib/site"

export function LandingHero() {
  return (
    <section className="relative isolate overflow-x-clip overflow-y-visible border-b border-border bg-background">
      <div className="relative mx-auto grid min-h-[calc(100svh-4rem)] w-full max-w-6xl items-center gap-10 px-6 py-16 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:gap-12 lg:py-20">
        <FadeIn className="flex flex-col gap-6">
          <div className="flex items-center gap-3">
            <RemitXLogo className="size-12 md:size-14" />
            <span className="font-heading text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
              {SITE_NAME}
            </span>
          </div>

          <h1 className="max-w-xl text-3xl font-semibold tracking-tight text-balance text-foreground md:text-4xl lg:text-5xl">
            Send ZAR. Land RLUSD for the people who need it.
          </h1>

          <p className="max-w-lg text-base text-muted-foreground md:text-lg">
            Cross-border remittance with fees you see upfront — settle on the
            XRP Ledger Testnet. Academic prototype. No real funds.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button
              size="lg"
              nativeButton={false}
              render={<Link to="/sign-up" />}
            >
              Start sending
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
        </FadeIn>

        <FadeIn
          delay={0.12}
          className="relative h-[min(62vh,34rem)] w-full overflow-visible lg:h-[min(82vh,46rem)]"
        >
          <LazyGlobeDemo className="absolute inset-0" />
        </FadeIn>
      </div>
    </section>
  )
}
