import { FadeIn } from "~/components/aceternity/fade-in"
import { HeroParallax } from "~/components/aceternity/hero-parallax"
import {
  PARALLAX_SCREENS,
  ProductScreen,
} from "~/components/landing/product-screen"

export function LandingParallax() {
  return (
    <HeroParallax
      header={
        <FadeIn>
          <div className="flex max-w-2xl flex-col gap-3">
            <p className="text-sm font-semibold tracking-wide text-primary uppercase">
              Both jobs
            </p>
            <h2 className="font-heading text-3xl font-semibold tracking-tight text-balance text-foreground md:text-5xl">
              A send and a stokvel, on the same account.
            </h2>
            <p className="text-base text-muted-foreground md:text-lg">
              Sample figures from both products, mixed together. The live ones
              show up after you sign in.
            </p>
          </div>
        </FadeIn>
      }
      cards={PARALLAX_SCREENS.map((screen) => ({
        title: `${screen.kicker}: ${screen.title}`,
        content: <ProductScreen screen={screen} />,
      }))}
    />
  )
}
