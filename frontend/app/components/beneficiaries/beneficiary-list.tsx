import {
  DotsThreeVerticalIcon,
  PaperPlaneTiltIcon,
  PencilSimpleIcon,
  TrashIcon,
} from "@phosphor-icons/react"
import { useState } from "react"
import { Link } from "react-router"

import type { BeneficiaryRead } from "~/client"
import { EditBeneficiaryDialog } from "~/components/beneficiaries/edit-beneficiary-dialog"
import { RemoveBeneficiaryDialog } from "~/components/beneficiaries/remove-beneficiary-dialog"
import { Avatar, AvatarFallback } from "~/components/ui/avatar"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { Skeleton } from "~/components/ui/skeleton"
import {
  beneficiaryInitials,
  beneficiaryName,
  maskedContact,
  relationshipLabel,
} from "~/lib/beneficiaries"

export function BeneficiaryList({
  beneficiaries,
}: {
  beneficiaries: readonly BeneficiaryRead[]
}) {
  return (
    <ItemGroup>
      {beneficiaries.map((beneficiary) => (
        <BeneficiaryRow
          key={beneficiary.beneficiary_id}
          beneficiary={beneficiary}
        />
      ))}
    </ItemGroup>
  )
}

function BeneficiaryRow({ beneficiary }: { beneficiary: BeneficiaryRead }) {
  const name = beneficiaryName(beneficiary)
  const contact = maskedContact(beneficiary)

  return (
    <Item variant="outline" role="listitem">
      <ItemMedia>
        <Avatar>
          <AvatarFallback>{beneficiaryInitials(beneficiary)}</AvatarFallback>
        </Avatar>
      </ItemMedia>
      <ItemContent className="min-w-0">
        <ItemTitle>{name}</ItemTitle>
        <ItemDescription>
          {[
            beneficiary.country_name ?? "Country not verified",
            relationshipLabel(beneficiary.relationship),
          ].join(" · ")}
        </ItemDescription>
        {contact ? <ItemDescription>{contact}</ItemDescription> : null}
      </ItemContent>
      <ItemActions>
        <Badge variant="secondary">{beneficiary.payout_currency}</Badge>
        <BeneficiaryRowMenu beneficiary={beneficiary} name={name} />
      </ItemActions>
    </Item>
  )
}

function BeneficiaryRowMenu({
  beneficiary,
  name,
}: {
  beneficiary: BeneficiaryRead
  name: string
}) {
  // The dialogs live outside the menu, so closing the menu on select doesn't
  // unmount them.
  const [dialog, setDialog] = useState<"edit" | "remove" | null>(null)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Actions for ${name}`}
            />
          }
        >
          <DotsThreeVerticalIcon />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            render={
              <Link
                to={`/app/send?beneficiary=${encodeURIComponent(beneficiary.beneficiary_id)}`}
              />
            }
          >
            <PaperPlaneTiltIcon />
            Send money
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setDialog("edit")}>
            <PencilSimpleIcon />
            Edit
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onClick={() => setDialog("remove")}
          >
            <TrashIcon />
            Remove
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <EditBeneficiaryDialog
        beneficiary={beneficiary}
        open={dialog === "edit"}
        onOpenChange={(open) => setDialog(open ? "edit" : null)}
      />
      <RemoveBeneficiaryDialog
        beneficiary={beneficiary}
        open={dialog === "remove"}
        onOpenChange={(open) => setDialog(open ? "remove" : null)}
      />
    </>
  )
}

export function BeneficiaryListSkeleton() {
  return (
    <ItemGroup aria-busy="true" aria-label="Loading beneficiaries">
      {[0, 1, 2].map((index) => (
        <Item key={index} variant="outline">
          <ItemMedia>
            <Skeleton className="size-8 rounded-full" />
          </ItemMedia>
          <ItemContent>
            <Skeleton className="h-3.5 w-40" />
            <Skeleton className="h-3 w-56" />
          </ItemContent>
          <ItemActions>
            <Skeleton className="h-5 w-10" />
          </ItemActions>
        </Item>
      ))}
    </ItemGroup>
  )
}
