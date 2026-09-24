import {
  DotsThreeVerticalIcon,
  PaperPlaneTiltIcon,
  PencilSimpleIcon,
  TrashIcon,
} from "@phosphor-icons/react"
import { useState } from "react"
import { Link } from "react-router"

import type { BeneficiaryRead } from "~/client"
import { BeneficiaryAvatar } from "~/components/beneficiaries/beneficiary-avatar"
import { EditBeneficiaryForm } from "~/components/beneficiaries/edit-beneficiary-form"
import { RemoveBeneficiaryDialog } from "~/components/beneficiaries/remove-beneficiary-dialog"
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
  const [editing, setEditing] = useState(false)
  const [removing, setRemoving] = useState(false)

  if (editing) {
    return (
      <EditBeneficiaryForm
        beneficiary={beneficiary}
        onCancel={() => setEditing(false)}
        onSaved={() => setEditing(false)}
      />
    )
  }

  return (
    <>
      <Item variant="outline" role="listitem">
        <ItemMedia>
          <BeneficiaryAvatar beneficiary={beneficiary} />
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
          <BeneficiaryRowMenu
            beneficiary={beneficiary}
            name={name}
            onEdit={() => setEditing(true)}
            onRemove={() => setRemoving(true)}
          />
        </ItemActions>
      </Item>
      <RemoveBeneficiaryDialog
        beneficiary={beneficiary}
        open={removing}
        onOpenChange={setRemoving}
      />
    </>
  )
}

function BeneficiaryRowMenu({
  beneficiary,
  name,
  onEdit,
  onRemove,
}: {
  beneficiary: BeneficiaryRead
  name: string
  onEdit: () => void
  onRemove: () => void
}) {
  return (
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
        <DropdownMenuItem onClick={onEdit}>
          <PencilSimpleIcon />
          Edit
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={onRemove}>
          <TrashIcon />
          Remove
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
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
