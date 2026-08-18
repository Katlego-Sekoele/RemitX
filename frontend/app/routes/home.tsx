import {
  CardBody,
  CardContainer,
  CardItem,
} from "~/components/aceternity/3d-card"
import { FadeIn } from "~/components/aceternity/fade-in"
import { GridBackground } from "~/components/aceternity/grid-background"
import { SpotlightCard } from "~/components/aceternity/spotlight-card"
import { Badge } from "~/components/ui/badge"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import type { Route } from "./+types/home"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "RemitX — Coming soon" },
    {
      name: "description",
      content:
        "Cross-border remittance from South African rand to RLUSD on the XRP Ledger Testnet.",
    },
  ]
}

export default function Home() {
  return (
    <GridBackground>
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-16">
        <main className="flex w-full max-w-lg flex-col items-stretch gap-6">
          <FadeIn className="w-full self-stretch">
            <CardContainer containerClassName="w-full py-0" className="w-full">
              <CardBody className="h-auto w-full">
                <CardItem translateZ={40} className="w-full">
                  <SpotlightCard className="w-full">
                    <Card className="w-full">
                      <CardHeader className="justify-items-center text-center">
                        <CardItem translateZ={60} className="mx-auto">
                          <img
                            src="/remitx-logo.svg"
                            alt="RemitX"
                            width={112}
                            height={112}
                            className="size-28"
                          />
                        </CardItem>
                        <CardItem translateZ={30}>
                          <Badge variant="secondary">Under construction</Badge>
                        </CardItem>
                        <CardItem translateZ={50}>
                          <CardTitle>RemitX</CardTitle>
                        </CardItem>
                        <CardItem translateZ={20} className="w-full">
                          <CardDescription>
                            A cross-border FX remittance prototype for sending
                            South African rand and settling in RLUSD on the XRP
                            Ledger Testnet. Built for UCT ECO5040W — academic
                            prototype only, no real funds.
                          </CardDescription>
                        </CardItem>
                      </CardHeader>
                    </Card>
                  </SpotlightCard>
                </CardItem>
              </CardBody>
            </CardContainer>
          </FadeIn>
          <FadeIn className="self-center" delay={0.15}>
            <CardDescription className="max-w-sm text-center">
              We&apos;re wiring up accounts, KYC, quotes, and async settlement.
              Check back soon.
            </CardDescription>
          </FadeIn>
        </main>
      </div>
    </GridBackground>
  )
}
