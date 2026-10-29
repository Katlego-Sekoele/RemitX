import { SITE_NAME } from "~/lib/site"

export function LandingFooter() {
  return (
    <footer className="px-6 py-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 text-sm text-muted-foreground">
        <p className="font-heading font-medium text-foreground">
          {SITE_NAME} · Remittance and stokvels · UCT ECO5040W and ECO5037W
        </p>
        <p>
          Academic prototype on the XRPL EVM Testnet. UCTUSD stands in for
          RLUSD. No real customer funds or production transfers.
        </p>
      </div>
    </footer>
  )
}
