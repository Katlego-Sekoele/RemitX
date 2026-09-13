import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router"

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
import { errorMessage, useOnboarding } from "~/hooks/use-onboarding"
import { KYC_ONBOARDING_KEY, pathForStep } from "~/lib/kyc-onboarding"
import { useApi } from "~/lib/use-api"

const COPY: Record<string, { title: string; body: string }> = {
  not_started: {
    title: "Not started",
    body: "You have not sent an application yet.",
  },
  in_progress: {
    title: "In progress",
    body: "Your draft is saved.",
  },
  submitted: {
    title: "With a reviewer",
    body: "We're reviewing your application.",
  },
  under_review: {
    title: "Under review",
    body: "A reviewer is looking at your application.",
  },
  more_info_required: {
    title: "More information needed",
    body: "Update your application and submit again.",
  },
  approved: {
    title: "Approved",
    body: "You're verified and can start sending.",
  },
  rejected: {
    title: "Not approved",
    body: "Start a new application. Your previous answers are filled in.",
  },
  review_due: {
    title: "Refresh due",
    body: "Your approval still stands, but a periodic review is due.",
  },
}

export default function Status() {
  const api = useApi()
  const onboarding = useOnboarding()
  const queryClient = useQueryClient()
  const status = onboarding.application?.status ?? onboarding.standing.status
  const copy = COPY[status] ?? COPY.not_started
  const start = useMutation({
    mutationFn: () => api.startKycOnboarding(),
    onSuccess: (data) => {
      queryClient.setQueryData(KYC_ONBOARDING_KEY, data)
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{copy.title}</CardTitle>
        <CardDescription>{copy.body}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {onboarding.rejection_reason ? (
          <p>{onboarding.rejection_reason}</p>
        ) : null}
      </CardContent>
      <CardFooter className="flex flex-col items-stretch gap-3">
        {start.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Could not start</AlertTitle>
            <AlertDescription>{errorMessage(start.error)}</AlertDescription>
          </Alert>
        ) : null}
        {status === "rejected" ||
        status === "review_due" ||
        status === "not_started" ? (
          <Button onClick={() => start.mutate()} disabled={start.isPending}>
            {start.isPending ? "Starting…" : "Start an application"}
          </Button>
        ) : null}
        {status === "in_progress" || status === "more_info_required" ? (
          <Button
            nativeButton={false}
            render={<Link to={pathForStep(onboarding.next_step)} />}
          >
            Continue
          </Button>
        ) : null}
        {start.data ? (
          <Button
            nativeButton={false}
            render={<Link to={pathForStep(start.data.next_step)} />}
          >
            Continue
          </Button>
        ) : null}
      </CardFooter>
    </Card>
  )
}
