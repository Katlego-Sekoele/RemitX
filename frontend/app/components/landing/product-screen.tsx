import { Badge } from "~/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { SETTLEMENT_TOKEN_LABEL } from "~/lib/money"
import { cn } from "~/lib/utils"

export type ProductScreenData = {
  title: string
  kicker: "Send" | "Stokvel"
  status: string
  figure: string
  figureLabel: string
  rows: { label: string; value: string }[]
}

const token = SETTLEMENT_TOKEN_LABEL

export const SEND_PREVIEW: ProductScreenData = {
  title: "Quote to Harare",
  kicker: "Send",
  status: "Sample",
  figure: "R2,500.00",
  figureLabel: `They receive ${token} 128.40`,
  rows: [
    { label: "Remittance fee", value: "R25.00" },
    { label: "FX margin", value: "1.50%" },
    { label: "Cash-in", value: "Confirmed" },
  ],
}

export const STOKVEL_PREVIEW: ProductScreenData = {
  title: "Family circle",
  kicker: "Stokvel",
  status: "Sample",
  figure: "Round 2 of 3",
  figureLabel: "R500.00 each, at today's rate",
  rows: [
    { label: "Paid this round", value: "2 of 3" },
    { label: "Pool", value: "Held in the contract" },
    { label: "Payout", value: "A remittance to Harare" },
  ],
}

/** Alternating send and stokvel screens for the parallax rows. */
export const PARALLAX_SCREENS: ProductScreenData[] = [
  SEND_PREVIEW,
  STOKVEL_PREVIEW,
  {
    title: "Fee lines",
    kicker: "Send",
    status: "Quoted",
    figure: "R2,543.40",
    figureLabel: "What you pay, before you confirm",
    rows: [
      { label: "Amount", value: "R2,500.00" },
      { label: "Remittance fee", value: "R25.00" },
      { label: "FX margin", value: "R18.40" },
    ],
  },
  {
    title: "This round",
    kicker: "Stokvel",
    status: "Unpaid",
    figure: "R500.00",
    figureLabel: "Your contribution, fee share on top",
    rows: [
      { label: "Members", value: "3" },
      { label: "Already paid", value: "2" },
      { label: "Payments", value: "One per member" },
    ],
  },
  {
    title: "Cash-in",
    kicker: "Send",
    status: "Waiting",
    figure: "R2,500.00",
    figureLabel: "Settlement waits for this",
    rows: [
      { label: "Reference", value: "RX-2041" },
      { label: "Beneficiary", value: "Harare · ZWL" },
      { label: token, value: "Burn waits on cash-in" },
    ],
  },
  {
    title: "Payout order",
    kicker: "Stokvel",
    status: "Locked",
    figure: "Member 2",
    figureLabel: "This round's beneficiary",
    rows: [
      { label: "Next", value: "Member 3" },
      { label: "Then", value: "Member 1" },
      { label: "Route", value: "Cross-border send" },
    ],
  },
  {
    title: "Settlement",
    kicker: "Send",
    status: "Settling",
    figure: `${token} 128.40`,
    figureLabel: "Burn on the XRPL EVM Testnet",
    rows: [
      { label: "Worker", value: "Queued" },
      { label: "Retry", value: "Pays once" },
      { label: "Cash-out", value: "Simulated" },
    ],
  },
  {
    title: "Pool",
    kicker: "Stokvel",
    status: "Held",
    figure: `${token} 120.00`,
    figureLabel: "Released only when the round is complete",
    rows: [
      { label: "Contract", value: "Stokvel vault" },
      { label: "Unpaid members", value: "1" },
      { label: "Early release", value: "Waits for every member" },
    ],
  },
  {
    title: "Wallet",
    kicker: "Send",
    status: "Received",
    figure: `${token} 128.40`,
    figureLabel: "Custodial balance after settlement",
    rows: [
      { label: "From", value: "Johannesburg" },
      { label: "Landed", value: "Harare" },
      { label: "Cash-out", value: "Available" },
    ],
  },
  {
    title: "Invitation",
    kicker: "Stokvel",
    status: "Open",
    figure: "Family circle",
    figureLabel: "Fixed contribution for the life of the stokvel",
    rows: [
      { label: "Each round", value: "R500.00" },
      { label: "Seats", value: "2 of 3 filled" },
      { label: "Payout", value: "Your beneficiary" },
    ],
  },
  {
    title: "Limits",
    kicker: "Send",
    status: "Verified",
    figure: "R25,000.00",
    figureLabel: "Left to send today",
    rows: [
      { label: "Monthly", value: "R100,000.00" },
      { label: "KYC", value: "Approved" },
      { label: "Unverified", value: "Sends stay closed" },
    ],
  },
  {
    title: "Cycle",
    kicker: "Stokvel",
    status: "Closed",
    figure: "3 of 3",
    figureLabel: "Everyone has been paid once",
    rows: [
      { label: "Each payout", value: "A remittance" },
      { label: "Next", value: "Continue or leave" },
      { label: "Amount", value: "Still R500.00" },
    ],
  },
  {
    title: "History",
    kicker: "Send",
    status: "Settled",
    figure: "RX-2041",
    figureLabel: "Last transfer",
    rows: [
      { label: "You sent", value: "R2,500.00" },
      { label: "They got", value: `${token} 128.40` },
      { label: "Chain", value: "XRPL EVM Testnet" },
    ],
  },
  {
    title: "Blocked round",
    kicker: "Stokvel",
    status: "Held",
    figure: "1 unpaid",
    figureLabel: "The pool does not move early",
    rows: [
      { label: "Payout time", value: "Passed" },
      { label: "Release", value: "Waiting on a member" },
      { label: "Beneficiary", value: "Payout still waiting" },
    ],
  },
  {
    title: "Both on one account",
    kicker: "Send",
    status: "Ready",
    figure: "Send + circle",
    figureLabel: "A stokvel payout uses this send path",
    rows: [
      { label: "Own transfer", value: "Quote, cash-in, settle" },
      { label: "Circle payout", value: "Same rails" },
      { label: "Funds", value: "Testnet only" },
    ],
  },
]

export function ProductScreen({
  screen,
  glass = false,
  className,
}: {
  screen: ProductScreenData
  glass?: boolean
  className?: string
}) {
  return (
    <Card
      size="sm"
      className={cn(
        "h-full w-full justify-between",
        glass && "bg-card/95 backdrop-blur-md",
        className
      )}
    >
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <Badge variant="outline">{screen.kicker}</Badge>
          <Badge variant="secondary">{screen.status}</Badge>
        </div>
        <CardDescription className="pt-3">{screen.title}</CardDescription>
        <CardTitle className="text-2xl tracking-tight">
          {screen.figure}
        </CardTitle>
        <CardDescription>{screen.figureLabel}</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="flex flex-col">
          {screen.rows.map((row) => (
            <div
              key={row.label}
              className="flex items-baseline justify-between gap-4 border-b border-border py-2 last:border-b-0"
            >
              <dt className="text-muted-foreground">{row.label}</dt>
              <dd className="text-right font-medium text-foreground">
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
