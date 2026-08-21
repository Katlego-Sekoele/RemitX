import { SITE_NAME } from "~/lib/site"

export function LandingFooter() {
  return (
    <footer className="border-t border-border px-6 py-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 text-sm text-muted-foreground">
        <p className="font-heading font-medium text-foreground">
          {SITE_NAME} · UCT ECO5040W Financial Software Engineering
        </p>
        <p>
          Academic prototype on XRPL Testnet. No real customer funds or
          production remittances.
        </p>
      </div>
    </footer>
  )
}
