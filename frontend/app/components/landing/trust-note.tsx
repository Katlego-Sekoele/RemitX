import { FadeIn } from "~/components/aceternity/fade-in"
import { FeaturesSectionCards } from "~/components/aceternity/features-section-cards"

const FEATURES = [
  {
    title: "Fees you can actually read",
    description:
      "Fixed remittance fee, percentage fee, FX margin, and cash-out fee — shown before you confirm.",
  },
  {
    title: "Limits that protect you",
    description:
      "Daily and monthly caps by KYC level. Unverified sends nothing; verified unlocks real headroom.",
  },
  {
    title: "KYC before big sends",
    description:
      "Simplified identity collection with admin approve/reject — gates how much you can remit.",
  },
  {
    title: "Cash-in first, always",
    description:
      "UCTUSD never moves until simulated ZAR payment is confirmed. No premature settlement.",
  },
  {
    title: "Async ledger settlement",
    description:
      "Transfers run through a queue so the UI stays snappy while Testnet does the heavy lifting.",
  },
  {
    title: "No double-crediting",
    description:
      "Duplicate-message protection on the worker so a retry cannot pay the recipient twice.",
  },
  {
    title: "Keys stay encrypted",
    description:
      "XRPL private keys are encrypted at rest and never returned by the API or dumped in logs.",
  },
  {
    title: "Built for the course brief",
    description:
      "Queue-backed settlement, encrypted keys, and KYC gates — the graded remittance path end to end.",
  },
]

export function TrustNote() {
  return (
    <section className="border-t border-border bg-muted/40 px-6 py-20 lg:py-28">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-12">
        <FadeIn>
          <div className="flex flex-col gap-3">
            <p className="text-sm font-semibold tracking-wide text-primary uppercase">
              Why RemitX
            </p>
            <h2 className="max-w-2xl font-heading text-3xl font-semibold tracking-tight text-balance text-foreground md:text-4xl">
              Remittance muscle without the black box.
            </h2>
            <p className="max-w-xl text-base text-muted-foreground md:text-lg">
              Built like a serious fintech product for individuals — clear
              quotes, gated limits, and settlement you can trust.
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
