import { FadeIn } from "~/components/aceternity/fade-in"
import { FeaturesSectionCards } from "~/components/aceternity/features-section-cards"

const FEATURES = [
  {
    title: "Fees on the quote",
    description:
      "Remittance fee, FX margin, and what the recipient gets — shown before you confirm a send or a stokvel payout.",
  },
  {
    title: "Cash-in, then settle",
    description:
      "The test token burns only after simulated rand cash-in is confirmed.",
  },
  {
    title: "One payout, even on retry",
    description:
      "The worker treats a duplicate message as the same payout, so a transfer or a round is credited once.",
  },
  {
    title: "Limits by KYC",
    description:
      "Daily and monthly caps follow your verification level, for sends and for contributions.",
  },
  {
    title: "The contract holds the pool",
    description:
      "Stokvel contributions sit in the vault on the XRPL EVM Testnet until the round's rules are met.",
  },
  {
    title: "A round pays abroad",
    description:
      "The member scheduled for that round names a beneficiary. The payout is a remittance to them.",
  },
  {
    title: "Keys stay encrypted",
    description:
      "The treasury key is encrypted at rest. The API never returns it, and it is not written to logs.",
  },
  {
    title: "Testnet, on purpose",
    description:
      "UCTUSD stands in for RLUSD. Academic prototype — no real customer funds.",
  },
]

export function TrustNote() {
  return (
    <section
      id="why"
      className="scroll-mt-24 border-b border-border bg-muted/40 px-6 py-20 lg:py-28"
    >
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-12">
        <FadeIn>
          <div className="flex max-w-2xl flex-col gap-3">
            <p className="text-sm font-semibold tracking-wide text-primary uppercase">
              Why both can share a platform
            </p>
            <h2 className="font-heading text-3xl font-semibold tracking-tight text-balance text-foreground md:text-4xl">
              The circle uses the same rails as a send.
            </h2>
            <p className="text-base text-muted-foreground md:text-lg">
              Quotes, limits, cash-in, and settlement serve a transfer you start
              yourself and a stokvel round paying one member.
            </p>
          </div>
        </FadeIn>

        <FadeIn delay={0.08}>
          <FeaturesSectionCards features={FEATURES} />
        </FadeIn>
      </div>
    </section>
  )
}
