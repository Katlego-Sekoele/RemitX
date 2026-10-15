import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { Link, useSearchParams } from "react-router"

import { api } from "~/client"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { CreateAmountStep } from "~/components/stokvels/create-amount-step"
import { CreateNameStep } from "~/components/stokvels/create-name-step"
import { CreateProgress } from "~/components/stokvels/create-progress"
import { CreateReviewStep } from "~/components/stokvels/create-review-step"
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
import {
  contributionIssue,
  createStepNumber,
  DEFAULT_STOKVEL_CURRENCY,
  firstPayoutDate,
  firstPayoutIssue,
  generateSchedule,
  membersIssue,
  nameIssue,
  readCreateSearch,
  resolveCreateStep,
  scheduleIssues,
  writeCreateSearch,
  type CreateSearch,
} from "~/lib/stokvel-create"
import { stokvelsPath } from "~/lib/stokvels"
import type { Route } from "./+types/stokvel-new"

// Nested under the Stokvels sidebar entry: that module owns the title.
const ROUTE_MODULE = "routes/app/stokvels.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "New stokvel — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * Create a stokvel (R4-03, #252): name, amount and schedule, review. Only a
 * KYC-approved user can create one (`POST /stokvels`, #229). Inviting
 * members is #253 and the payout order is #255; both happen on the stokvel's
 * setup page after creation.
 */
export default function StokvelNewPage() {
  const onboarding = useQuery(api.kyc.onboarding.getApplication())
  const verified = isKycVerified(onboarding.data?.standing)

  return (
    <AppPageFrame
      module={ROUTE_MODULE}
      title="New stokvel"
      parents={[{ label: "Stokvels", href: stokvelsPath() }]}
    >
      <div className="flex w-full max-w-2xl flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>New stokvel</PageHeaderTitle>
          <PageHeaderDescription>
            Set the amount and the payout days, then invite the members.
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
          <CreateFlow />
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
          Only verified customers can start a stokvel. Finish verification to
          continue.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button nativeButton={false} render={<Link to={verificationPath()} />}>
          Continue verification
        </Button>
        <Button
          variant="ghost"
          nativeButton={false}
          render={<Link to={stokvelsPath()} />}
        >
          Back to stokvels
        </Button>
      </CardContent>
    </Card>
  )
}

function CreateFlow() {
  const [params, setParams] = useSearchParams()
  const search = readCreateSearch(params)
  const accounts = useQuery(api.accounts.getAccounts())

  // The Stokvel currency is one the organiser holds a fiat account in; ZAR
  // is the default and the one every customer has from signup.
  const currencies = useMemo(() => {
    const held =
      accounts.data
        ?.filter((account) => account.kind === "fiat")
        .map((account) => account.currency) ?? []
    return held.length > 0 ? held : [DEFAULT_STOKVEL_CURRENCY]
  }, [accounts.data])
  const currency =
    search.currency && currencies.includes(search.currency)
      ? search.currency
      : DEFAULT_STOKVEL_CURRENCY

  const schedule = useMemo(() => {
    const first = firstPayoutDate(search.firstPayout, search.time)
    if (!first || membersIssue(search.members)) return null
    return generateSchedule({
      firstPayout: first,
      frequency: search.frequency,
      rounds: search.members,
    })
  }, [search.firstPayout, search.time, search.members, search.frequency])

  const nameValid = nameIssue(search.name) === null
  const amountValid =
    contributionIssue(search.amount) === null &&
    membersIssue(search.members) === null &&
    firstPayoutIssue(search.firstPayout, search.time) === null &&
    schedule !== null &&
    scheduleIssues(schedule).length === 0
  const step = resolveCreateStep(search, nameValid, amountValid)
  const maxStep = !nameValid
    ? createStepNumber("name")
    : amountValid
      ? createStepNumber("review")
      : createStepNumber("amount")

  /** Step changes are history entries; typing replaces the current one. */
  function update(patch: Partial<CreateSearch>, replace = false) {
    setParams(writeCreateSearch(search, patch), {
      replace,
      preventScrollReset: true,
    })
  }

  return (
    <div className="flex flex-col gap-6">
      <CreateProgress
        step={step}
        maxStep={maxStep}
        onStepChange={(next) => update({ step: next })}
      />
      {step === "name" ? (
        <CreateNameStep
          name={search.name}
          goal={search.goal}
          currency={currency}
          currencies={currencies}
          onNameChange={(name) => update({ name }, true)}
          onGoalChange={(goal) => update({ goal }, true)}
          onCurrencyChange={(next) => update({ currency: next }, true)}
          onContinue={() => update({ step: "amount" })}
        />
      ) : step === "amount" ? (
        <CreateAmountStep
          search={search}
          currency={currency}
          schedule={schedule}
          onChange={(patch) => update(patch, true)}
          onBack={() => update({ step: "name" })}
          onContinue={() => update({ step: "review" })}
        />
      ) : schedule ? (
        <CreateReviewStep
          search={search}
          currency={currency}
          schedule={schedule}
          onBack={() => update({ step: "amount" })}
        />
      ) : null}
    </div>
  )
}
