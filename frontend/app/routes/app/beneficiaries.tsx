import { UsersThreeIcon } from "@phosphor-icons/react"

import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { Button } from "~/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import type { Route } from "./+types/beneficiaries"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"

const ROUTE_MODULE = "routes/app/beneficiaries.tsx"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Beneficiaries — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function BeneficiariesPage() {
  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>Beneficiaries</PageHeaderTitle>
          <PageHeaderDescription>
            People you send money to.
          </PageHeaderDescription>
        </PageHeader>

        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <UsersThreeIcon />
            </EmptyMedia>
            <EmptyTitle>No beneficiaries yet</EmptyTitle>
            <EmptyDescription>Add a recipient to get started.</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button disabled aria-disabled="true">
              Add beneficiary
            </Button>
            <EmptyDescription>
              Adding beneficiaries isn&apos;t available yet.
            </EmptyDescription>
          </EmptyContent>
        </Empty>
      </div>
    </AppPageFrame>
  )
}
