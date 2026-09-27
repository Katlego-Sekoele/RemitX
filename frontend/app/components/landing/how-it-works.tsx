import {
  CurrencyCircleDollarIcon,
  IdentificationCardIcon,
  QueueIcon,
  ReceiptIcon,
  SealCheckIcon,
  UserCirclePlusIcon,
  WalletIcon,
  BankIcon,
} from "@phosphor-icons/react"

import { FadeIn } from "~/components/aceternity/fade-in"
import { FeaturesSectionHover } from "~/components/aceternity/features-section-hover"

const FEATURES = [
  {
    icon: (
      <UserCirclePlusIcon className="size-6" weight="duotone" aria-hidden />
    ),
    title: "Create your account",
    description:
      "Sign up in seconds and start a send flow built for individuals — not corporate seats.",
  },
  {
    icon: (
      <IdentificationCardIcon className="size-6" weight="duotone" aria-hidden />
    ),
    title: "Mock KYC, then go",
    description:
      "Complete simplified identity checks so verified limits unlock before you remit.",
  },
  {
    icon: (
      <CurrencyCircleDollarIcon
        className="size-6"
        weight="duotone"
        aria-hidden
      />
    ),
    title: "Quote ZAR → UCTUSD",
    description:
      "Enter how much rand you want to send and see the live FX path to UCTUSD.",
  },
  {
    icon: <ReceiptIcon className="size-6" weight="duotone" aria-hidden />,
    title: "Every fee, upfront",
    description:
      "Remittance fee, FX margin, and what the recipient gets — no surprise math later.",
  },
  {
    icon: <SealCheckIcon className="size-6" weight="duotone" aria-hidden />,
    title: "Confirm cash-in",
    description:
      "Simulate paying ZAR. Settlement never starts until cash-in is confirmed.",
  },
  {
    icon: <QueueIcon className="size-6" weight="duotone" aria-hidden />,
    title: "Settle on Testnet",
    description:
      "A background worker pushes UCTUSD on the XRP Ledger Testnet — async, not fragile.",
  },
  {
    icon: <WalletIcon className="size-6" weight="duotone" aria-hidden />,
    title: "Receive in-wallet",
    description:
      "Recipients open a custodial web wallet and see UCTUSD land where it belongs.",
  },
  {
    icon: <BankIcon className="size-6" weight="duotone" aria-hidden />,
    title: "Cash out if you want",
    description:
      "Keep UCTUSD or request a simulated fiat cash-out when they need local money.",
  },
]

export function HowItWorks() {
  return (
    <section className="border-t border-border px-6 py-20 lg:py-28">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-12">
        <FadeIn>
          <div className="flex flex-col gap-3 px-0 md:px-2">
            <p className="text-sm font-semibold tracking-wide text-primary uppercase">
              How sending works
            </p>
            <h2 className="max-w-2xl font-heading text-3xl font-semibold tracking-tight text-balance text-foreground md:text-4xl">
              From rand in your pocket to UCTUSD in theirs.
            </h2>
            <p className="max-w-xl text-base text-muted-foreground md:text-lg">
              A full remittance journey for people who send money — quote,
              cash-in, settle, receive.
            </p>
          </div>
        </FadeIn>

        <FadeIn delay={0.08}>
          <FeaturesSectionHover features={FEATURES} />
        </FadeIn>
      </div>
    </section>
  )
}
