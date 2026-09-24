import {
  EyeSlashIcon,
  IdentificationCardIcon,
  ScalesIcon,
  ShieldCheckIcon,
} from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Navigate, useNavigate } from "react-router"

import { SecurityOnIllustration } from "~/components/illustrations/security-on"
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
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage, storeApplication } from "~/hooks/use-onboarding"
import {
  applicationPath,
  applicationStepPath,
  canStartApplication,
  isOpenStatus,
  verificationPath,
} from "~/lib/kyc-onboarding"
import { api } from "~/client"

const REASONS = [
  {
    icon: ScalesIcon,
    title: "The law requires it",
    body: "Anyone moving money across borders must confirm who their customers are.",
  },
  {
    icon: ShieldCheckIcon,
    title: "It protects you",
    body: "It stops anyone else from sending money in your name.",
  },
  {
    icon: EyeSlashIcon,
    title: "It stays private",
    body: "Staff see your details masked. Only reviewers can open your documents, and every view is logged.",
  },
]

/** Starting an application. Residence is asked on the address step, which
 * (with submit) enforces where RemitX operates. An open application is
 * resumed instead, and a customer whose approval still stands has nothing to
 * start. */
export default function NewApplication() {
  const standing = useQuery(api.kyc.onboarding.getApplication())

  if (standing.isPending) return <Skeleton className="h-40 w-full" />
  if (standing.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Could not load your verification</AlertTitle>
        <AlertDescription>{errorMessage(standing.error)}</AlertDescription>
      </Alert>
    )
  }

  const current = standing.data.application
  if (current && isOpenStatus(current.status)) {
    return <Navigate to={applicationPath(current.application_id)} replace />
  }
  if (!canStartApplication(standing.data.standing.status)) {
    return <Navigate to={verificationPath()} replace />
  }

  return (
    <div className="mx-auto w-full max-w-2xl">
      <StartCard />
    </div>
  )
}

function StartCard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const start = useMutation({
    ...api.kyc.onboarding.startApplication(),
    onSuccess: (data) => {
      storeApplication(queryClient, data)
      const id = data.application.application_id
      navigate(
        applicationStepPath(
          id,
          data.next_step === "welcome" ? "identity" : data.next_step
        )
      )
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>New application</CardTitle>
        <CardDescription>Takes about five minutes.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <SecurityOnIllustration className="mx-auto h-auto w-full max-w-xs" />
        <div className="flex flex-col gap-2">
          <p>Why we ask for your details:</p>
          <ItemGroup>
            {REASONS.map((reason) => (
              <Item
                key={reason.title}
                size="sm"
                role="listitem"
                className="px-0"
              >
                <ItemMedia variant="icon">
                  <reason.icon />
                </ItemMedia>
                <ItemContent>
                  <ItemTitle>{reason.title}</ItemTitle>
                  <ItemDescription className="line-clamp-none">
                    {reason.body}
                  </ItemDescription>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        </div>
        <div className="flex flex-col gap-2">
          <p>Have these to hand:</p>
          <ul className="list-disc space-y-1 pl-4">
            <li>Your national ID number, or your passport</li>
            <li>A photo of that document</li>
            <li>Proof of address (a recent utility bill or bank statement)</li>
            <li>Your mobile number and the name as it appears on the ID</li>
          </ul>
        </div>
        <p>You can leave and come back — your progress is saved.</p>
      </CardContent>
      <CardFooter className="flex flex-col items-stretch gap-3">
        {start.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Could not start</AlertTitle>
            <AlertDescription>{errorMessage(start.error)}</AlertDescription>
          </Alert>
        ) : null}
        <Button
          type="button"
          disabled={start.isPending}
          onClick={() => start.mutate({})}
        >
          <IdentificationCardIcon />
          {start.isPending ? "Starting…" : "Continue"}
        </Button>
      </CardFooter>
    </Card>
  )
}
