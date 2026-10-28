import { Badge } from "~/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { FadeIn } from "~/components/aceternity/fade-in"

const PATHS = [
  {
    id: "send",
    kicker: "Send",
    title: "Remit rand across the border",
    description:
      "A transfer of your own. The person you name receives the settlement token, or a simulated cash-out.",
    steps: [
      {
        title: "Quote in rand",
        description:
          "Remittance fee, FX margin, and what they receive are on the quote before you confirm.",
      },
      {
        title: "Confirm cash-in",
        description:
          "Settlement starts once the simulated rand payment is confirmed.",
      },
      {
        title: "Settle on testnet",
        description:
          "A worker burns the test token on the XRPL EVM Testnet. A retry still pays the recipient once.",
      },
      {
        title: "They receive it",
        description:
          "The beneficiary opens a custodial wallet, or requests a simulated cash-out.",
      },
    ],
  },
  {
    id: "stokvel",
    kicker: "Stokvel",
    title: "Pool a round, pay one member",
    description:
      "A rotating savings circle. Everyone contributes. One member's beneficiary is paid each round, through the send path above.",
    steps: [
      {
        title: "Open a circle",
        description:
          "Name it, set a fixed contribution, and invite members. The amount stays fixed for the life of the stokvel.",
      },
      {
        title: "Pay the round",
        description:
          "Each member contributes once. The contract records who has paid.",
      },
      {
        title: "Release the pool",
        description:
          "When everyone has paid and the payout time has passed, the pool is released to that round's beneficiary as a remittance.",
      },
      {
        title: "Close the cycle",
        description:
          "After every member has been paid once, the cycle ends. Members continue into the next one, or leave.",
      },
    ],
  },
] as const

export function LandingPaths() {
  return (
    <section className="border-b border-border px-6 py-20 lg:py-28">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-12">
        <FadeIn>
          <div className="flex max-w-2xl flex-col gap-3">
            <p className="text-sm font-semibold tracking-wide text-primary uppercase">
              How it fits together
            </p>
            <h2 className="font-heading text-3xl font-semibold tracking-tight text-balance text-foreground md:text-5xl">
              Two products. The payout is shared.
            </h2>
            <p className="text-base text-muted-foreground md:text-lg">
              Use RemitX to send, to run a stokvel, or both. A round pays out as
              a remittance, on the same path as a transfer you send yourself.
            </p>
          </div>
        </FadeIn>

        <div className="grid items-start gap-6 lg:grid-cols-2">
          {PATHS.map((path, pathIndex) => (
            <FadeIn key={path.id} delay={pathIndex * 0.08}>
              <Card id={path.id} className="scroll-mt-24">
                <CardHeader>
                  <Badge variant="outline" className="w-fit">
                    {path.kicker}
                  </Badge>
                  <CardTitle className="pt-2 text-2xl">{path.title}</CardTitle>
                  <CardDescription className="text-sm">
                    {path.description}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ol className="flex flex-col gap-5">
                    {path.steps.map((step, index) => (
                      <li
                        key={step.title}
                        className="grid grid-cols-[auto_minmax(0,1fr)] gap-3"
                      >
                        <Badge variant="secondary">{index + 1}</Badge>
                        <div className="flex flex-col gap-1">
                          <p className="font-medium text-foreground">
                            {step.title}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {step.description}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ol>
                </CardContent>
              </Card>
            </FadeIn>
          ))}
        </div>
      </div>
    </section>
  )
}
