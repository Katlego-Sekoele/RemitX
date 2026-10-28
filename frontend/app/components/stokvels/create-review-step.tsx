import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router"
import { mutationToast } from "~/lib/mutation-toast"

import { api } from "~/client"
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
import { useTokenRate } from "~/hooks/use-token-rate"
import { currencyName, formatMoney } from "~/lib/money"
import { normalizeAmount } from "~/lib/send"
import {
  createStokvelRequest,
  LIVE_RATE_HINT,
  type CreateSearch,
} from "~/lib/stokvel-create"
import { invalidateStokvels, stokvelPath } from "~/lib/stokvels"

export function CreateReviewStep({
  search,
  currency,
  onBack,
}: {
  search: CreateSearch
  /** The resolved Stokvel currency: shown here and sent in the body. */
  currency: string
  onBack: () => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  // The amount is stored as UCTUSD bought at this rate (D13), so the stokvel
  // can't be created until the rate has loaded.
  const rate = useTokenRate(currency)
  const create = useMutation({
    ...mutationToast(api.stokvels.createStokvel(), {
      success: (stokvel) => `${stokvel.name} created`,
    }),
    onSuccess: async (stokvel) => {
      await invalidateStokvels(queryClient)
      navigate(stokvelPath(stokvel.stokvel_id))
    },
  })

  const amount = normalizeAmount(search.amount)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review</CardTitle>
        <CardDescription>
          Creating the stokvel charges nobody. Next you invite members and, once
          they&apos;ve joined, set the payout order and days and start the
          cycle.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>Name</DescriptionTerm>
            <DescriptionDetails>{search.name.trim()}</DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Currency</DescriptionTerm>
            <DescriptionDetails>
              {currency} · {currencyName(currency)}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Each member pays</DescriptionTerm>
            <DescriptionDetails>
              about {formatMoney(amount, currency)} per round at today&apos;s
              rate, plus a fee share
            </DescriptionDetails>
          </DescriptionItem>
        </DescriptionList>
        <p className="text-sm text-muted-foreground">{LIVE_RATE_HINT}</p>
        {rate.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Couldn&apos;t get today&apos;s rate</AlertTitle>
            <AlertDescription>{errorMessage(rate.error)}</AlertDescription>
          </Alert>
        ) : null}
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
          disabled={create.isPending || !rate.data}
          onClick={() => {
            if (rate.data) {
              create.mutate({
                body: createStokvelRequest(search, currency, rate.data),
              })
            }
          }}
        >
          {create.isPending
            ? "Creating…"
            : rate.isPending
              ? "Getting today's rate…"
              : "Create stokvel"}
        </Button>
      </CardFooter>
    </Card>
  )
}
