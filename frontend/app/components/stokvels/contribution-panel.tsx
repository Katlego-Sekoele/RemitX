import type { ReactNode } from "react"
import { ArrowSquareOutIcon, CheckCircleIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { format } from "date-fns"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import { api } from "~/client"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "~/components/ui/sheet"
import { Skeleton } from "~/components/ui/skeleton"
import { useFeeShareEstimate } from "~/hooks/use-fee-share"
import { ACCOUNTS_HREF } from "~/lib/accounts"
import {
  amountToCents,
  formatMoney,
  subtractMoney,
  sumMoney,
} from "~/lib/money"
import { skipMutationToast } from "~/lib/mutation-toast"
import {
  contributeRefusal,
  contributeRefusalMessage,
  isFinalRefusal,
} from "~/lib/stokvel-errors"
import {
  contributionProofHash,
  explorerTxUrl,
  invalidateStokvels,
  roundLabel,
  stokvelMutations,
  type StokvelRoundContributionRead,
  type StokvelDetailRead,
  type StokvelRoundRead,
} from "~/lib/stokvels"

/**
 * "Your contribution" for the open round: the amount due and Pay now, a
 * confirm sheet, Confirming…, then Paid with the proof link. The member pays
 * a fee share on top (D6): an estimate before paying, the API's `fee_amount`
 * after. Refusals show the doc §6 wording; a low balance points at the
 * deposit screen.
 */
export function ContributionPanel({
  stokvel,
  round,
  mine,
  outstanding,
  availableBalance,
  bare = false,
}: {
  stokvel: StokvelDetailRead
  round: StokvelRoundRead
  /** The member's own contribution to this round, if any. */
  mine: StokvelRoundContributionRead | undefined
  /** Members still to pay, the member included while unpaid. */
  outstanding: number
  availableBalance: string | undefined
  /** Sit inside another card (the pot) instead of drawing its own. */
  bare?: boolean
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  // The toast follows the chain, which settles after this request returns.
  const contribute = useMutation({
    ...skipMutationToast(stokvelMutations.contribute(stokvel.stokvel_id)),
    onSuccess: async () => {
      await invalidateStokvels(queryClient)
    },
    onSettled: async () => {
      // A refusal may still have changed what the API knows (e.g. already
      // paid), so the page re-reads either way.
      await invalidateStokvels(queryClient)
      await queryClient.invalidateQueries({
        queryKey: api.accounts.getAccounts().queryKey,
      })
    },
  })

  const amount = stokvel.contribution_fiat_estimate
  const currency = stokvel.currency
  const paid = mine?.status === "confirmed"
  const toastId = `contribution-${stokvel.stokvel_id}-${round.round}`
  const sawInflight = useRef(false)
  const confirming =
    contribute.isPending ||
    mine?.status === "pending" ||
    mine?.status === "processing"
  useEffect(() => {
    if (confirming) {
      sawInflight.current = true
      toast.loading("Confirming your contribution…", { id: toastId })
      return
    }
    if (!sawInflight.current) return
    sawInflight.current = false
    if (paid) {
      toast.success(
        `Paid ${roundLabel(round.round, stokvel.total_rounds ?? round.round + 1)}`,
        { id: toastId }
      )
    } else if (mine?.status === "failed") {
      toast.error("The contribution didn't go through", { id: toastId })
    } else if (contribute.isError) {
      toast.dismiss(toastId)
    }
  }, [
    confirming,
    contribute.isError,
    mine?.status,
    paid,
    round.round,
    stokvel.total_rounds,
    toastId,
  ])
  const refusal = contribute.isError
    ? contributeRefusal(contribute.error)
    : null

  // The recipient's payout currency sets the margin; only their own is known.
  const recipientIsMe = round.recipient_member_id === stokvel.my_member_id
  const estimate = useFeeShareEstimate({
    contribution: amount ?? "0",
    currency,
    memberCount: stokvel.member_count,
    payoutCurrency: recipientIsMe
      ? (stokvel.my_beneficiary?.payout_currency ?? null)
      : null,
    enabled: !mine && amount != null,
  })
  const proof = mine ? contributionProofHash(mine) : null
  const actualFee = mine?.fee_amount ?? contribute.data?.fee_amount
  const fee = actualFee ?? estimate.data

  if (!amount && !paid && !confirming) {
    return (
      <Frame bare={bare}>
        <CardHeader>
          <CardTitle>Your contribution</CardTitle>
          <CardDescription>
            Today&apos;s exchange rate is unavailable, so this round can&apos;t
            be paid yet.
          </CardDescription>
        </CardHeader>
      </Frame>
    )
  }

  // The API refuses unless the balance covers the contribution and the fee.
  const needed = amount == null ? null : fee ? sumMoney([amount, fee]) : amount
  const paidFigure = amount ?? mine?.amount_fiat ?? null
  const lowBalance =
    needed != null &&
    availableBalance !== undefined &&
    amountToCents(availableBalance) < amountToCents(needed)

  if (paid || confirming) {
    return (
      <Frame bare={bare}>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle>Your contribution</CardTitle>
            <Badge variant={paid ? "default" : "secondary"}>
              {paid ? (
                <>
                  <CheckCircleIcon data-icon="inline-start" /> Paid
                </>
              ) : (
                "Confirming…"
              )}
            </Badge>
          </div>
          <CardDescription>
            {paid
              ? outstanding === 0
                ? `Everyone has paid. The payout is released on ${format(new Date(round.payout_time), "EEE d MMM 'at' HH:mm")}.`
                : `Waiting for ${outstanding} more ${outstanding === 1 ? "member" : "members"}. If one member hasn't paid, the payout waits for them.`
              : "Your payment is being confirmed. This usually takes a few seconds; the page updates on its own."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <span className="flex flex-col">
            <span className="font-heading text-3xl font-bold tabular-nums">
              {paidFigure
                ? formatMoney(paidFigure, currency)
                : "Rate unavailable"}
            </span>
            {actualFee ? (
              <span className="text-xs text-muted-foreground">
                + {formatMoney(actualFee, currency)} fee share
              </span>
            ) : null}
          </span>
          {proof ? (
            <Button
              variant="link"
              size="sm"
              nativeButton={false}
              render={
                <a
                  href={explorerTxUrl(proof)}
                  target="_blank"
                  rel="noreferrer"
                />
              }
            >
              Proof of payment
              <ArrowSquareOutIcon data-icon="inline-end" aria-hidden="true" />
            </Button>
          ) : null}
        </CardContent>
      </Frame>
    )
  }

  // Past the pay-by time: still accepted, with no penalty (D7); the payout
  // waits for everyone (D12).
  const late = Date.now() > Date.parse(round.deadline)

  return (
    <Frame bare={bare}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>Your contribution</CardTitle>
          <Badge variant={late ? "outline" : "secondary"}>
            {late ? "Late, no penalty" : "Waiting for you"}
          </Badge>
        </div>
        <CardDescription>
          {late ? "Was due" : "Due"}{" "}
          {format(new Date(round.deadline), "EEE d MMM, HH:mm")} · payout{" "}
          {format(new Date(round.payout_time), "EEE d MMM, HH:mm")}
          {availableBalance !== undefined
            ? ` · balance ${formatMoney(availableBalance, currency)}`
            : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-heading text-3xl font-bold tabular-nums">
            {amount ? formatMoney(amount, currency) : "Rate unavailable"}
          </span>
          {lowBalance && needed != null && availableBalance !== undefined ? (
            <Button nativeButton={false} render={<Link to={ACCOUNTS_HREF} />}>
              Top up{" "}
              {formatMoney(subtractMoney(needed, availableBalance), currency)}{" "}
              first
            </Button>
          ) : (
            <Button onClick={() => setOpen(true)}>Pay now</Button>
          )}
        </div>
        {refusal ? (
          <Alert variant="destructive">
            <AlertTitle>
              {refusal === "contribution_already_paid"
                ? "Already paid"
                : "Couldn't pay this round"}
            </AlertTitle>
            <AlertDescription>
              {contributeRefusalMessage(refusal, contribute.error)}
              {refusal === "insufficient_balance" ? (
                <>
                  {" "}
                  <Link to={ACCOUNTS_HREF} className="underline">
                    Add money
                  </Link>
                </>
              ) : null}
            </AlertDescription>
          </Alert>
        ) : null}
        <p className="text-xs text-muted-foreground">
          You also pay a share of the payout fee, so the beneficiary gets the
          full pool. Top up 2 days before your due date; deposits take time to
          confirm. Contributions and fees count toward your sending limits.
        </p>
      </CardContent>
      <CardFooter className="text-xs text-muted-foreground">
        Your money is held safely until payout day. Nobody, not even the
        organiser, can take it early.
      </CardFooter>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="bottom" className="sm:mx-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>
              Pay {roundLabel(round.round, stokvel.total_rounds ?? 0)}
            </SheetTitle>
            <SheetDescription>
              From your {currency} account, at today&apos;s rate.
            </SheetDescription>
          </SheetHeader>
          <div className="flex flex-col gap-4 px-4">
            <span className="font-heading text-3xl font-bold tabular-nums">
              {fee ? "about " : ""}
              {needed ? formatMoney(needed, currency) : "Rate unavailable"}
            </span>
            <DescriptionList>
              <DescriptionItem>
                <DescriptionTerm>Contribution</DescriptionTerm>
                <DescriptionDetails>
                  {amount ? formatMoney(amount, currency) : "Rate unavailable"}
                </DescriptionDetails>
              </DescriptionItem>
              <DescriptionItem>
                <DescriptionTerm>
                  Your share of the payout fee, paid on top
                </DescriptionTerm>
                <DescriptionDetails>
                  {estimate.isPending && !actualFee ? (
                    <Skeleton className="h-4 w-16" />
                  ) : fee ? (
                    `about ${formatMoney(fee, currency)}`
                  ) : (
                    "Worked out when you pay"
                  )}
                </DescriptionDetails>
              </DescriptionItem>
              {availableBalance !== undefined && needed != null ? (
                <DescriptionItem>
                  <DescriptionTerm>Balance after</DescriptionTerm>
                  <DescriptionDetails>
                    {formatMoney(
                      subtractMoney(availableBalance, needed),
                      currency
                    )}
                  </DescriptionDetails>
                </DescriptionItem>
              ) : null}
            </DescriptionList>
            <p className="text-xs text-muted-foreground">
              The exact fee share is set when you pay, at that moment&apos;s
              rate. Contributions and fees count toward your sending limits.
              Your money is held safely until payout day.
            </p>
          </div>
          <SheetFooter>
            <Button
              disabled={contribute.isPending}
              onClick={() => {
                setOpen(false)
                contribute.mutate(undefined, {
                  onError: (error) => {
                    if (isFinalRefusal(contributeRefusal(error))) {
                      toast.error(
                        contributeRefusalMessage(
                          contributeRefusal(error),
                          error
                        )
                      )
                    }
                  },
                })
              }}
            >
              Confirm payment
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </Frame>
  )
}

/** Own card, or the right-hand side of the pot card. */
function Frame({ bare, children }: { bare: boolean; children: ReactNode }) {
  if (bare) {
    return (
      <div className="flex min-w-0 flex-1 flex-col gap-(--card-spacing)">
        {children}
      </div>
    )
  }
  return <Card>{children}</Card>
}
