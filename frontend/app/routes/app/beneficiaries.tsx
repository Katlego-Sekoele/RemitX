import { ArrowClockwiseIcon, UsersThreeIcon } from "@phosphor-icons/react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { api } from "~/client"
import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import {
  BeneficiaryList,
  BeneficiaryListSkeleton,
} from "~/components/beneficiaries/beneficiary-list"
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { errorMessage } from "~/hooks/use-onboarding"
import {
  BENEFICIARY_SORT_LABELS,
  type BeneficiarySort,
} from "~/lib/beneficiaries"
import type { Route } from "./+types/beneficiaries"

const ROUTE_MODULE = "routes/app/beneficiaries.tsx"

const SORT_ITEMS = (
  Object.keys(BENEFICIARY_SORT_LABELS) as BeneficiarySort[]
).map((value) => ({ value, label: BENEFICIARY_SORT_LABELS[value] }))

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Beneficiaries — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function BeneficiariesPage() {
  const [sort, setSort] = useState<BeneficiarySort>("newest")
  const beneficiaries = useQuery({
    ...api.beneficiaries.listMyBeneficiaries({ query: { sort } }),
    // A new sort is a new query: keep the current rows up while it loads
    // rather than flashing the skeleton.
    placeholderData: keepPreviousData,
  })

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <PageHeader>
            <PageHeaderTitle>Beneficiaries</PageHeaderTitle>
            <PageHeaderDescription>
              People you send money to.
            </PageHeaderDescription>
          </PageHeader>
          <div className="flex items-center gap-2">
            <Select
              items={SORT_ITEMS}
              value={sort}
              onValueChange={(next) => {
                if (next) setSort(next as BeneficiarySort)
              }}
            >
              <SelectTrigger className="w-28" aria-label="Sort beneficiaries">
                <SelectValue />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {SORT_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <AddBeneficiaryButton />
          </div>
        </div>

        {beneficiaries.isPending ? (
          <BeneficiaryListSkeleton />
        ) : beneficiaries.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Couldn&apos;t load your beneficiaries</AlertTitle>
            <AlertDescription>
              {errorMessage(beneficiaries.error)}
            </AlertDescription>
            <AlertAction>
              <Button
                variant="outline"
                size="sm"
                disabled={beneficiaries.isFetching}
                onClick={() => beneficiaries.refetch()}
              >
                <ArrowClockwiseIcon data-icon="inline-start" />
                Retry
              </Button>
            </AlertAction>
          </Alert>
        ) : beneficiaries.data.length === 0 ? (
          <Empty className="border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <UsersThreeIcon />
              </EmptyMedia>
              <EmptyTitle>No beneficiaries yet</EmptyTitle>
              <EmptyDescription>
                Add a recipient to get started.
              </EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <AddBeneficiaryButton />
            </EmptyContent>
          </Empty>
        ) : (
          <BeneficiaryList beneficiaries={beneficiaries.data} />
        )}
      </div>
    </AppPageFrame>
  )
}

function AddBeneficiaryButton() {
  return (
    <Button disabled aria-disabled="true">
      Add beneficiary
    </Button>
  )
}
