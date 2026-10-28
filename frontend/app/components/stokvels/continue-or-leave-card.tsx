import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useMutation } from "~/hooks/use-mutation"
import { useState } from "react"
import { useNavigate } from "react-router"
import { api } from "~/client"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog"
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
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "~/components/ui/field"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { beneficiaryName } from "~/lib/beneficiaries"
import { stokvelErrorMessage } from "~/lib/stokvel-errors"
import {
  continuationStatus,
  invalidateStokvels,
  stokvelMutations,
  stokvelsPath,
  type StokvelDetailRead,
} from "~/lib/stokvels"

/** The Select's value for "carry over the beneficiary I had". */
const KEEP = "keep"

/**
 * After a cycle closes (R4-10, #259): a member who hasn't answered chooses to
 * continue into the next cycle, keeping their payout beneficiary or picking
 * another, or to leave (`POST /stokvels/{id}/members/me/continuation`,
 * #237). Leaving is final and asks first. A member who continued sees that,
 * and can still leave until the cycle starts. The Organiser is always
 * continued, so sees nothing here. Not answering by the start counts as
 * leaving, and the card says so.
 */
export function ContinueOrLeaveCard({
  stokvel,
}: {
  stokvel: StokvelDetailRead
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const status = continuationStatus(stokvel)
  const [beneficiaryId, setBeneficiaryId] = useState(KEEP)
  const [confirmLeave, setConfirmLeave] = useState(false)
  const beneficiaries = useQuery({
    ...api.beneficiaries.listMyBeneficiaries(),
    enabled: status === "undecided",
  })

  const decide = useMutation({
    ...stokvelMutations.continueOrLeave(stokvel.stokvel_id),
    toast: {
      success: (result) =>
        result.choice === "leave"
          ? `You've left ${stokvel.name}`
          : `You're in for cycle ${result.cycle_number}`,
    },
    onSuccess: async (result) => {
      if (result.choice === "leave") {
        setConfirmLeave(false)
        // No longer a member: the page would answer 404.
        await navigate(stokvelsPath())
        await invalidateStokvels(queryClient)
        return
      }
      await invalidateStokvels(queryClient)
    },
  })

  if (status === "none" || status === "organiser") return null

  const next = stokvel.cycle?.cycle_number ?? 2
  const closed = stokvel.previous_cycle?.cycle_number ?? next - 1
  const items = [
    { value: KEEP, label: "Keep my current beneficiary" },
    ...(beneficiaries.data ?? []).map((b) => ({
      value: b.beneficiary_id,
      label: `${beneficiaryName(b)} · ${b.payout_currency}`,
    })),
  ]
  const leaving = decide.isPending && decide.variables?.choice === "leave"

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>
            {status === "continued"
              ? `You're in for cycle ${next}`
              : `Cycle ${closed} is done`}
          </CardTitle>
          {status === "continued" ? <Badge>Continuing</Badge> : null}
        </div>
        <CardDescription>
          {status === "continued"
            ? `Your payout for cycle ${next} is below, and you can change it. You can still leave until the organiser starts the cycle.`
            : `Everyone has been paid once. Continue into cycle ${next}, or leave the stokvel. If you haven't answered when the organiser starts cycle ${next}, you're treated as leaving.`}
        </CardDescription>
      </CardHeader>
      {status === "undecided" ? (
        <CardContent>
          <Field>
            <FieldLabel htmlFor="continue-beneficiary">
              Your payout in cycle {next}
            </FieldLabel>
            <Select
              items={items}
              value={beneficiaryId}
              onValueChange={(value) => setBeneficiaryId(value ?? KEEP)}
            >
              <SelectTrigger id="continue-beneficiary" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {items.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {decide.isError && !confirmLeave ? (
              <FieldError>{stokvelErrorMessage(decide.error)}</FieldError>
            ) : (
              <FieldDescription>
                Paid in that beneficiary&apos;s saved payout currency, like last
                cycle.
              </FieldDescription>
            )}
          </Field>
        </CardContent>
      ) : decide.isError && !confirmLeave ? (
        <CardContent>
          <FieldError>{stokvelErrorMessage(decide.error)}</FieldError>
        </CardContent>
      ) : null}
      <CardFooter className="flex-wrap justify-between gap-2">
        <Button
          variant="ghost"
          disabled={decide.isPending}
          onClick={() => {
            decide.reset()
            setConfirmLeave(true)
          }}
        >
          Leave the stokvel
        </Button>
        {status === "undecided" ? (
          <Button
            disabled={decide.isPending}
            onClick={() =>
              decide.mutate({
                choice: "continue",
                beneficiary_id: beneficiaryId === KEEP ? null : beneficiaryId,
              })
            }
          >
            {decide.isPending && !leaving
              ? "Saving…"
              : `Continue into cycle ${next}`}
          </Button>
        ) : null}
      </CardFooter>

      <AlertDialog
        open={confirmLeave}
        onOpenChange={(open) => {
          // Not mid-request: closing would drop the leave's own error.
          if (!open && decide.isPending) return
          setConfirmLeave(open)
          if (!open) decide.reset()
        }}
      >
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Leave {stokvel.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              You won&apos;t be in cycle {next}, and coming back needs a new
              invitation from the organiser.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {decide.isError ? (
            <FieldError>{stokvelErrorMessage(decide.error)}</FieldError>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={decide.isPending}>
              Stay
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={decide.isPending}
              onClick={(event) => {
                // Stay open until the leave has gone through or failed.
                event.preventDefault()
                decide.mutate({ choice: "leave" })
              }}
            >
              {leaving ? "Leaving…" : "Leave"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
