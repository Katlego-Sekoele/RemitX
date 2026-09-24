import { useQuery } from "@tanstack/react-query"
import { Link, useSearchParams } from "react-router"

import { api, type KycStandingRead as KycStanding } from "~/client"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { AmountStep } from "~/components/send/amount-step"
import { RecipientStep } from "~/components/send/recipient-step"
import { ReviewStep } from "~/components/send/review-step"
import { SendProgress } from "~/components/send/send-progress"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import { isKycVerified, verificationPath } from "~/lib/kyc-onboarding"
import { amountToCents, fromCents } from "~/lib/money"
import {
  amountIssue,
  isPayoutCurrency,
  PAYOUT_CURRENCIES,
  readSendSearch,
  resolveStep,
  SENDER_CURRENCY,
  stepNumber,
  writeSendSearch,
  type AmountLimits,
  type PayoutCurrency,
  type SendSearch,
} from "~/lib/send"
import type { Route } from "./+types/send"

const ROUTE_MODULE = "routes/app/send.tsx"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Send — RemitX" }, { name: "robots", content: "noindex" }]
}

function asAmount(value: string | undefined): string | undefined {
  if (value === undefined) return undefined
  try {
    return fromCents(amountToCents(value))
  } catch {
    return undefined
  }
}

/**
 * What's left to send. Until KYC-3 (#25) reports usage, that's the whole of
 * the tier's limits; the API still refuses a quote over its own ceiling.
 */
function limitsFrom(
  standing: KycStanding | undefined,
  available: string | undefined
): AmountLimits {
  return {
    available: asAmount(available),
    dailyRemaining: asAmount(standing?.daily_limit_zar),
    monthlyRemaining: asAmount(standing?.monthly_limit_zar),
  }
}

export default function SendPage() {
  const onboarding = useQuery(api.kyc.onboarding.getApplication())
  const standing = onboarding.data?.standing
  const verified = isKycVerified(standing?.status)

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex max-w-2xl flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>Send money</PageHeaderTitle>
          <PageHeaderDescription>
            From your ZAR balance to someone in your beneficiaries.
          </PageHeaderDescription>
        </PageHeader>
        {onboarding.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : onboarding.isError ? (
          <Card>
            <CardHeader>
              <CardTitle>Couldn&apos;t check your verification</CardTitle>
              <CardDescription>
                {errorMessage(onboarding.error)}
              </CardDescription>
            </CardHeader>
          </Card>
        ) : !verified ? (
          <VerificationRequired />
        ) : (
          <SendFlow standing={standing} />
        )}
      </div>
    </AppPageFrame>
  )
}

function VerificationRequired() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Verification required</CardTitle>
        <CardDescription>
          Only verified customers can send money. Finish verification to start
          sending.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button nativeButton={false} render={<Link to={verificationPath()} />}>
          Continue verification
        </Button>
      </CardContent>
    </Card>
  )
}

function AddMoney() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Add money</CardTitle>
        <CardDescription>
          Your ZAR balance is empty. Pay in by EFT using your ZAR account
          reference; the transfer can be sent once we&apos;ve confirmed the
          deposit. You can still see what an amount would cost below.
        </CardDescription>
      </CardHeader>
    </Card>
  )
}

function SendFlow({ standing }: { standing: KycStanding | undefined }) {
  const [params, setParams] = useSearchParams()
  const search = readSendSearch(params)

  const beneficiaries = useQuery(api.beneficiaries.listMyBeneficiaries())
  const accounts = useQuery(api.accounts.getAccounts())

  const zarAccount = accounts.data?.find(
    (account) => account.currency === SENDER_CURRENCY
  )
  const limits = limitsFrom(standing, zarAccount?.available_balance)
  const emptyBalance =
    zarAccount !== undefined &&
    amountToCents(zarAccount.available_balance) <= 0n

  const beneficiary =
    beneficiaries.data?.find(
      (candidate) => candidate.beneficiary_id === search.beneficiaryId
    ) ?? null
  // A stale or foreign id in the URL sends the sender back to pick again.
  const missing =
    Boolean(search.beneficiaryId) && beneficiaries.isSuccess && !beneficiary
  const effective: SendSearch = missing
    ? { ...search, beneficiaryId: null }
    : search

  const amountValid = amountIssue(search.amount, limits) === null
  const step =
    beneficiaries.isPending && search.beneficiaryId
      ? null
      : resolveStep(effective, amountValid)
  const maxStep = !beneficiary
    ? stepNumber("recipient")
    : amountValid
      ? stepNumber("review")
      : stepNumber("amount")

  /** Step changes are history entries; typing replaces the current one. */
  function update(patch: Partial<SendSearch>, replace = false) {
    setParams(writeSendSearch(effective, patch), {
      replace,
      preventScrollReset: true,
    })
  }

  const currency: PayoutCurrency =
    search.currency ??
    (beneficiary && isPayoutCurrency(beneficiary.payout_currency)
      ? beneficiary.payout_currency
      : PAYOUT_CURRENCIES[0])

  return (
    <div className="flex flex-col gap-6">
      {step ? (
        <SendProgress
          step={step}
          maxStep={maxStep}
          onStepChange={(next) => update({ step: next })}
        />
      ) : null}
      {emptyBalance ? <AddMoney /> : null}
      {step === null ? (
        <Skeleton className="h-40 w-full" />
      ) : step === "recipient" || !beneficiary ? (
        <RecipientStep
          beneficiaries={beneficiaries.data ?? []}
          loading={beneficiaries.isPending}
          error={beneficiaries.error}
          selected={beneficiary}
          missing={missing}
          onSelect={(next) =>
            update(
              {
                beneficiaryId: next?.beneficiary_id ?? null,
                // A new recipient brings their own payout currency.
                currency: null,
                step: "recipient",
              },
              true
            )
          }
          onContinue={() => update({ step: "amount" })}
        />
      ) : step === "amount" ? (
        <AmountStep
          beneficiary={beneficiary}
          amount={search.amount}
          currency={currency}
          limits={limits}
          onAmountChange={(amount) => update({ amount }, true)}
          onCurrencyChange={(next) =>
            update(
              {
                // The beneficiary's own currency needs no override.
                currency: next === beneficiary.payout_currency ? null : next,
              },
              true
            )
          }
          onBack={() => update({ step: "recipient" })}
          onContinue={() => update({ step: "review" })}
        />
      ) : (
        <ReviewStep
          beneficiary={beneficiary}
          amount={search.amount}
          currency={currency}
          // A changed amount needs a new quote; the old one simply expires.
          onBack={() => update({ step: "amount" })}
        />
      )}
    </div>
  )
}
