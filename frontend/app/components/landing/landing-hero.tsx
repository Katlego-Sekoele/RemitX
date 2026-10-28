import { useRef, type PointerEvent } from "react"

import {
  AsciiTextField,
  createAsciiPointer,
} from "~/components/aceternity/ascii-text-field"
import { FadeIn } from "~/components/aceternity/fade-in"
import { LandingAuthActions } from "~/components/landing/landing-auth-actions"
import {
  ProductScreen,
  SEND_PREVIEW,
  STOKVEL_PREVIEW,
} from "~/components/landing/product-screen"
import { Badge } from "~/components/ui/badge"

export function LandingHero() {
  const pointerRef = useRef(createAsciiPointer())

  function onPointerMove(event: PointerEvent<HTMLElement>) {
    const bounds = event.currentTarget.getBoundingClientRect()
    pointerRef.current.tx = event.clientX - bounds.left
    pointerRef.current.ty = event.clientY - bounds.top
  }

  function onPointerLeave() {
    pointerRef.current.tx = -2000
    pointerRef.current.ty = -2000
  }

  return (
    <section
      className="relative isolate min-h-[calc(100svh-4rem)] overflow-hidden border-b border-border bg-background"
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
    >
      <AsciiTextField pointerRef={pointerRef} className="absolute inset-0" />
      <div className="relative z-10 mx-auto grid w-full max-w-6xl items-center gap-12 px-6 py-16 lg:min-h-[calc(100svh-4rem)] lg:grid-cols-2 lg:py-20">
        <FadeIn className="flex flex-col gap-6">
          <Badge variant="outline" className="w-fit">
            Remittance and stokvels
          </Badge>
          <h1 className="max-w-xl text-4xl font-semibold tracking-tight text-balance text-foreground md:text-6xl lg:text-7xl">
            Send across a border. Save in a circle.
          </h1>
          <p className="max-w-lg text-base text-muted-foreground md:text-lg">
            RemitX does both. Quote a rand transfer with every fee shown first,
            or run a rotating stokvel with people you trust. When a round pays
            out, that payout is a remittance.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <LandingAuthActions signUpLabel="Get started" />
          </div>
          <p className="max-w-md text-sm text-muted-foreground">
            XRPL EVM Testnet. Academic prototype — no real funds.
          </p>
        </FadeIn>

        <FadeIn delay={0.12} className="grid items-start gap-4 sm:grid-cols-2">
          <ProductScreen screen={SEND_PREVIEW} glass />
          <div className="sm:pt-14">
            <ProductScreen screen={STOKVEL_PREVIEW} glass />
          </div>
        </FadeIn>
      </div>
    </section>
  )
}
