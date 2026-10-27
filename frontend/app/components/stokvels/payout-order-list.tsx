import { DotsSixVerticalIcon } from "@phosphor-icons/react"
import { useUser } from "@clerk/react-router"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { api, type BeneficiaryRead } from "~/client"
import { BeneficiaryAvatar } from "~/components/beneficiaries/beneficiary-avatar"
import {
  Sortable,
  SortableItem,
  SortableItemHandle,
} from "~/components/reui/sortable"
import { Badge } from "~/components/ui/badge"
import { FieldDescription, FieldError } from "~/components/ui/field"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { beneficiaryName, beneficiaryShortName } from "~/lib/beneficiaries"
import { stokvelErrorMessage } from "~/lib/stokvel-errors"
import {
  joinedMemberIds,
  PAYOUT_ORDER_SAVE_DELAY_MS,
  ROSTER_STATUS_LABELS,
  sameIds,
  type RosterPerson,
} from "~/lib/stokvel-setup"
import {
  invalidateStokvels,
  plannedPayoutOrder,
  stokvelMutations,
  type StokvelDetailRead,
} from "~/lib/stokvels"

const personKey = (person: RosterPerson) => person.key

const STATUS_VARIANT = {
  organiser: "outline",
  accepted: "default",
  pending: "secondary",
} as const

function portrait(
  person: RosterPerson,
  beneficiaries: readonly BeneficiaryRead[],
  meImage: string | null | undefined
): BeneficiaryRead | { full_name: string; profile_image_url: string | null } {
  if (person.isMe && meImage) {
    return { full_name: person.name, profile_image_url: meImage }
  }
  const match = person.userId
    ? beneficiaries.find(
        (beneficiary) => beneficiary.linked_user_id === person.userId
      )
    : beneficiaries.find((beneficiary) => {
        const name = beneficiaryName(beneficiary)
        return (
          name === person.name ||
          beneficiaryShortName(beneficiary) === person.name
        )
      })
  return match ?? { full_name: person.name, profile_image_url: null }
}

function RosterRow({
  person,
  index,
  beneficiaries,
  meImage,
  handle,
}: {
  person: RosterPerson
  index: number
  beneficiaries: readonly BeneficiaryRead[]
  meImage: string | null | undefined
  handle: boolean
}) {
  return (
    <Item variant="outline">
      {handle ? (
        <SortableItemHandle
          className="text-muted-foreground"
          aria-label={`Drag ${person.name}`}
        >
          <DotsSixVerticalIcon />
        </SortableItemHandle>
      ) : null}
      <ItemMedia>
        <BeneficiaryAvatar
          beneficiary={portrait(person, beneficiaries, meImage)}
        />
      </ItemMedia>
      <ItemContent>
        <ItemTitle>{person.name}</ItemTitle>
        <ItemDescription>Round {index + 1}</ItemDescription>
      </ItemContent>
      <ItemActions>
        <Badge variant={STATUS_VARIANT[person.status]}>
          {ROSTER_STATUS_LABELS[person.status]}
        </Badge>
      </ItemActions>
    </Item>
  )
}

/** The invite list in payout order, for a member who isn't arranging it. */
export function RosterReadout({ roster }: { roster: readonly RosterPerson[] }) {
  const { user } = useUser()
  const beneficiaries = useQuery(api.beneficiaries.listMyBeneficiaries())
  const list = beneficiaries.data ?? []
  if (roster.length === 0) return null
  return (
    <ol className="flex flex-col gap-2">
      {roster.map((person, index) => (
        <li key={person.key}>
          <RosterRow
            person={person}
            index={index}
            beneficiaries={list}
            meImage={user?.imageUrl}
            handle={false}
          />
        </li>
      ))}
    </ol>
  )
}

/**
 * Drag to reorder the invite list. The new order is kept locally at once and
 * saved once the dragging pauses, so a reorder doesn't call the API per move.
 */
export function PayoutOrderList({
  stokvel,
  roster,
  onReorder,
}: {
  stokvel: StokvelDetailRead
  roster: RosterPerson[]
  onReorder: (next: RosterPerson[]) => void
}) {
  const queryClient = useQueryClient()
  const { user } = useUser()
  const beneficiaries = useQuery(api.beneficiaries.listMyBeneficiaries())
  const list = beneficiaries.data ?? []
  const toastId = `payout-order-${stokvel.stokvel_id}`
  const savedRef = useRef(plannedPayoutOrder(stokvel))
  savedRef.current = plannedPayoutOrder(stokvel)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingIds = useRef<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function saveIds(memberIds: string[]) {
    pendingIds.current = null
    if (memberIds.length === 0 || sameIds(memberIds, savedRef.current)) {
      toast.success("Payout order updated", { id: toastId })
      return
    }
    toast.loading("Saving payout order…", { id: toastId })
    try {
      await stokvelMutations
        .setPayoutOrder(stokvel.stokvel_id)
        .mutationFn({ member_ids: memberIds })
      savedRef.current = memberIds
      setError(null)
      await invalidateStokvels(queryClient)
      toast.success("Payout order saved", { id: toastId })
    } catch (caught) {
      setError(stokvelErrorMessage(caught))
      toast.error(stokvelErrorMessage(caught), { id: toastId })
    }
  }

  function queue(next: RosterPerson[]) {
    onReorder(next)
    const memberIds = joinedMemberIds(next)
    if (timer.current) clearTimeout(timer.current)
    pendingIds.current = memberIds
    timer.current = setTimeout(() => {
      void saveIds(memberIds)
    }, PAYOUT_ORDER_SAVE_DELAY_MS)
  }

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current)
      const memberIds = pendingIds.current
      if (!memberIds || sameIds(memberIds, savedRef.current)) return
      void stokvelMutations
        .setPayoutOrder(stokvel.stokvel_id)
        .mutationFn({ member_ids: memberIds })
      toast.success("Payout order saved", { id: toastId })
    }
  }, [stokvel.stokvel_id, toastId])

  return (
    <div className="flex flex-col gap-3">
      <FieldDescription>
        Drag to choose who is paid first. Someone who hasn&apos;t accepted yet
        can still be placed. The cycle starts once everyone on this list has
        joined.
      </FieldDescription>
      <Sortable
        value={roster}
        getItemValue={personKey}
        onValueChange={queue}
        strategy="vertical"
        className="flex flex-col gap-2"
      >
        {roster.map((person, index) => (
          <SortableItem key={person.key} value={person.key}>
            <RosterRow
              person={person}
              index={index}
              beneficiaries={list}
              meImage={user?.imageUrl}
              handle
            />
          </SortableItem>
        ))}
      </Sortable>
      {error ? <FieldError>{error}</FieldError> : null}
    </div>
  )
}
