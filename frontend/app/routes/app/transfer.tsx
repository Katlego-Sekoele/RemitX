import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { api, type TransferRead as Transfer } from "~/client"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { QuoteLines } from "~/components/send/quote-lines"
import { TransferStatusBadge } from "~/components/transfers/transfer-status-badge"
import { TransferTimeline } from "~/components/transfers/transfer-timeline"
import { XrplHash } from "~/components/transfers/xrpl-hash"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import { useNow } from "~/hooks/use-now"
import { formatMoney } from "~/lib/money"
import { SEND_PATH, writeSendSearch } from "~/lib/send"
import {
  formatWhen,
  isInFlight,
  isSlowToStart,
  POLL_INTERVAL_MS,
  TRANSFERS_PATH,
} from "~/lib/transfers"
import type { Route } from "./+types/transfer"

const ROUTE_MODULE = "routes/app/transfers.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Transfer — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

/** One transfer: its status as it settles, then the hash and a receipt.
 * Polls while the transfer is queued or settling, and stops once it has
 * completed or failed. */
export default function TransferPage({ params }: Route.ComponentProps) {
  const query = useQuery({
    ...api.remittances.getRemittance({
      path: { remittance_id: params.remittanceId },
    }),
    refetchInterval: (current) =>
      current.state.data && isInFlight(current.state.data.status)
        ? POLL_INTERVAL_MS
        : false,
  })

  return (
    <AppPageFrame
      module={ROUTE_MODULE}
      title="Transfer"
      parents={[{ label: "Transfers", href: TRANSFERS_PATH }]}
    >
      <div className="flex w-full max-w-2xl flex-col gap-6">
        {query.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : query.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Could not load this transfer</AlertTitle>
            <AlertDescription>{errorMessage(query.error)}</AlertDescription>
          </Alert>
        ) : (
          <TransferDetail transfer={query.data} />
        )}
      </div>
    </AppPageFrame>
  )
}

function TransferDetail({ transfer }: { transfer: Transfer }) {
  const sent = transfer.direction === "sent"
  const who = transfer.counterparty_name ?? "an unnamed recipient"
  const inFlight = isInFlight(transfer.status)

  return (
    <>
      <PageHeader>
        <PageHeaderTitle>
          {sent
            ? `To ${who}`
            : `From ${transfer.counterparty_name ?? "a sender"}`}
        </PageHeaderTitle>
        <PageHeaderDescription>
          {formatMoney(transfer.receiver_amount, transfer.receiver_currency)} ·{" "}
          {formatWhen(transfer.created_at)}
        </PageHeaderDescription>
      </PageHeader>

      <Card>
        <CardHeader>
          <CardTitle>Status</CardTitle>
          <CardDescription>
            {inFlight
              ? "This page updates by itself until the transfer settles."
              : null}
          </CardDescription>
          <CardAction>
            <TransferStatusBadge status={transfer.status} />
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {inFlight ? <SlowQueueNotice transfer={transfer} /> : null}
          <TransferTimeline transfer={transfer} />
          {transfer.status === "confirmed" && transfer.xrpl_tx_hash ? (
            <DescriptionList>
              <DescriptionItem>
                <DescriptionTerm>XRPL transaction</DescriptionTerm>
                <DescriptionDetails>
                  <XrplHash hash={transfer.xrpl_tx_hash} />
                </DescriptionDetails>
              </DescriptionItem>
              {transfer.settled_at ? (
                <DescriptionItem>
                  <DescriptionTerm>Settled</DescriptionTerm>
                  <DescriptionDetails>
                    {formatWhen(transfer.settled_at)}
                  </DescriptionDetails>
                </DescriptionItem>
              ) : null}
            </DescriptionList>
          ) : null}
          {transfer.status === "failed" ? (
            <Alert variant="destructive">
              <AlertTitle>This transfer didn&apos;t go through</AlertTitle>
              <AlertDescription>
                {sent
                  ? "Nothing was taken from your balance."
                  : "Nothing was paid into your account."}
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Receipt</CardTitle>
          <CardDescription>
            {sent
              ? `To ${who}, paid from your ZAR balance.`
              : `From ${transfer.counterparty_name ?? "a sender"}.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <QuoteLines quote={transfer} />
        </CardContent>
        <CardFooter className="flex flex-wrap justify-between gap-2">
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link to="/app" />}
          >
            Back to overview
          </Button>
          {sent ? <SendAgainButton transfer={transfer} /> : null}
        </CardFooter>
      </Card>
    </>
  )
}

/** The cloud worker is a free Render service woken on demand, so the first
 * transfer after it idles can sit queued for a while. */
function SlowQueueNotice({ transfer }: { transfer: Transfer }) {
  const now = useNow()
  if (!isSlowToStart(transfer.status, transfer.created_at, now)) return null
  return (
    <Alert aria-live="polite">
      <AlertTitle>Taking longer than usual</AlertTitle>
      <AlertDescription>
        The settlement worker may be waking up. This page keeps checking.
      </AlertDescription>
    </Alert>
  )
}

/** Back into the send flow with the same beneficiary picked. */
function SendAgainButton({ transfer }: { transfer: Transfer }) {
  const beneficiaries = useQuery(api.beneficiaries.listMyBeneficiaries())
  const match = beneficiaries.data?.find(
    (beneficiary) =>
      beneficiary.linked_user_id === transfer.counterparty_user_id
  )
  const search = match
    ? `?${writeSendSearch(
        { beneficiaryId: null, amount: "", currency: null, step: null },
        { beneficiaryId: match.beneficiary_id }
      )}`
    : ""
  return (
    <Button nativeButton={false} render={<Link to={`${SEND_PATH}${search}`} />}>
      Send again
    </Button>
  )
}
