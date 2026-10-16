import { useMutation, useQueryClient } from "@tanstack/react-query"
import { format } from "date-fns"
import { useNavigate } from "react-router"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
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
import { errorMessage } from "~/hooks/use-onboarding"
import { formatMoney } from "~/lib/money"
import { normalizeAmount } from "~/lib/send"
import {
  createStokvelRequest,
  FREQUENCIES,
  type CreateSearch,
} from "~/lib/stokvel-create"
import {
  invalidateStokvels,
  poolAmount,
  stokvelMutations,
  stokvelPath,
  type StokvelScheduleRound,
} from "~/lib/stokvels"

export function CreateReviewStep({
  search,
  currency,
  schedule,
  onBack,
}: {
  search: CreateSearch
  currency: string
  schedule: StokvelScheduleRound[]
  onBack: () => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const create = useMutation({
    ...stokvelMutations.create(),
    onSuccess: async (stokvel) => {
      await invalidateStokvels(queryClient)
      toast.success(`${stokvel.name} created`)
      navigate(stokvelPath(stokvel.stokvel_id))
    },
  })

  const amount = normalizeAmount(search.amount)
  const first = schedule[0]
  const last = schedule[schedule.length - 1]
  const frequency =
    FREQUENCIES.find((option) => option.key === search.frequency)?.label ??
    search.frequency

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review</CardTitle>
        <CardDescription>
          Creating the stokvel charges nobody. You invite members next, and
          start the cycle once at least two are ready.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>Name</DescriptionTerm>
            <DescriptionDetails>{search.name.trim()}</DescriptionDetails>
          </DescriptionItem>
          {search.goal.trim() ? (
            <DescriptionItem>
              <DescriptionTerm>Goal</DescriptionTerm>
              <DescriptionDetails>{search.goal.trim()}</DescriptionDetails>
            </DescriptionItem>
          ) : null}
          <DescriptionItem>
            <DescriptionTerm>Each member pays</DescriptionTerm>
            <DescriptionDetails>
              {formatMoney(amount, currency)} per round
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Pool per round</DescriptionTerm>
            <DescriptionDetails>
              {formatMoney(poolAmount(amount, search.members), currency)}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Rounds</DescriptionTerm>
            <DescriptionDetails>
              {schedule.length} · {frequency.toLowerCase()}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>First payout</DescriptionTerm>
            <DescriptionDetails>
              {format(new Date(first.payout_time), "EEE d MMM yyyy, HH:mm")}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Last payout</DescriptionTerm>
            <DescriptionDetails>
              {format(new Date(last.payout_time), "EEE d MMM yyyy, HH:mm")}
            </DescriptionDetails>
          </DescriptionItem>
        </DescriptionList>
        {create.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Couldn&apos;t create the stokvel</AlertTitle>
            <AlertDescription>{errorMessage(create.error)}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
      <CardFooter className="flex-wrap justify-between gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={create.isPending}
          onClick={onBack}
        >
          Back
        </Button>
        <Button
          type="button"
          disabled={create.isPending}
          onClick={() => create.mutate(createStokvelRequest(search, schedule))}
        >
          {create.isPending ? "Creating…" : "Create stokvel"}
        </Button>
      </CardFooter>
    </Card>
  )
}
