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
  nameIssue,
  readCreateSearch,
  resolveCreateCurrency,
  resolveCreateStep,
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
 * Create a stokvel (R4-03, #252): name, amount, review. Only a KYC-approved
 * user can create one (`POST /stokvels`, #229), which takes just the name,
 * currency and amount. Inviting members is #253; the payout days and payout
 * order are #255. Both happen on the stokvel's page after creation.
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
            Name it and set the amount. You invite members and choose the payout
            days next.
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
  // Shown on every step and sent in the body, so they always agree.
  const currency = resolveCreateCurrency(search.currency, currencies)

  const nameValid = nameIssue(search.name) === null
  const amountValid = contributionIssue(search.amount) === null
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
          currency={currency}
          currencies={currencies}
          onNameChange={(name) => update({ name }, true)}
          onCurrencyChange={(next) => update({ currency: next }, true)}
          onContinue={() => update({ step: "amount" })}
        />
      ) : step === "amount" ? (
        <CreateAmountStep
          search={search}
          currency={currency}
          onChange={(patch) => update(patch, true)}
          onBack={() => update({ step: "name" })}
          onContinue={() => update({ step: "review" })}
        />
      ) : (
        <CreateReviewStep
          search={search}
          currency={currency}
          onBack={() => update({ step: "amount" })}
        />
      )}
    </div>
  )
}
