import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useMutation } from "~/hooks/use-mutation"
import { format } from "date-fns"
import { useState } from "react"
import { QueryError } from "~/components/accounts/query-error"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
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
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
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
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "~/components/ui/field"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { Textarea } from "~/components/ui/textarea"
import { errorMessage } from "~/hooks/use-onboarding"
import {
  invalidateStokvelContract,
  PAUSE_REASON_MAX,
  pauseReasonIssue,
  stokvelContractMutations,
  stokvelContractQueries,
  type StokvelContractRead,
} from "~/lib/stokvel-contract"
import { explorerAddressUrl } from "~/lib/stokvels"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/stokvel-contract"

const ROUTE_MODULE = "routes/admin/stokvel-contract.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * The stokvel contract and its emergency stop (R4-07, #256): the current
 * state at a glance, Pause (with a required reason for the audit log) and
 * Resume. Reads and writes the live admin stokvel-contract API (#244, R4-09).
 */
export default function StokvelContractPage() {
  const contract = useQuery(stokvelContractQueries.status())

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>{pageRoutingContext?.title}</PageHeaderTitle>
          <PageHeaderDescription>
            Emergency stop for every stokvel. Pausing halts contributions and
            payouts; it never changes release conditions.
          </PageHeaderDescription>
        </PageHeader>

        {contract.isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : contract.isError ? (
          <QueryError
            title="Couldn't read the contract"
            error={contract.error}
            onRetry={() => contract.refetch()}
          />
        ) : (
          <ContractCard contract={contract.data} />
        )}
      </div>
    </AdminPageFrame>
  )
}

function ContractCard({ contract }: { contract: StokvelContractRead }) {
  const [dialog, setDialog] = useState<"pause" | "resume" | null>(null)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle>Contract</CardTitle>
          <Badge variant={contract.paused ? "destructive" : "outline"}>
            {contract.paused ? "Paused" : "Running"}
          </Badge>
        </div>
        <CardDescription>{contract.network}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {contract.paused ? (
          <Alert variant="destructive">
            <AlertTitle>
              Stokvels are paused
              {contract.paused_at
                ? ` since ${format(new Date(contract.paused_at), "EEE d MMM, HH:mm")}`
                : ""}
            </AlertTitle>
            <AlertDescription>
              Members can't pay and no payouts are released.
              {contract.paused_reason
                ? ` Reason: ${contract.paused_reason}`
                : ""}
            </AlertDescription>
          </Alert>
        ) : null}
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>Address</DescriptionTerm>
            <DescriptionDetails className="min-w-0 truncate font-mono">
              <a
                href={explorerAddressUrl(contract.address)}
                target="_blank"
                rel="noopener noreferrer"
              >
                {contract.address}
              </a>
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Treasury balance</DescriptionTerm>
            <DescriptionDetails className="tabular-nums">
              {contract.treasury_token_balance} UCTUSD
            </DescriptionDetails>
          </DescriptionItem>
        </DescriptionList>
      </CardContent>
      <CardFooter className="flex-wrap gap-2">
        {contract.paused ? (
          <Button onClick={() => setDialog("resume")}>
            Resume all stokvels
          </Button>
        ) : (
          <Button variant="destructive" onClick={() => setDialog("pause")}>
            Pause all stokvels
          </Button>
        )}
      </CardFooter>

      <PauseDialog
        open={dialog === "pause"}
        onOpenChange={(open) => setDialog(open ? "pause" : null)}
      />
      <ResumeDialog
        open={dialog === "resume"}
        onOpenChange={(open) => setDialog(open ? "resume" : null)}
      />
    </Card>
  )
}

/** Pausing affects every member, so it asks first and needs a reason for the
 * audit log (R3-12, #249). */
function PauseDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState("")
  const [touched, setTouched] = useState(false)
  const issue = pauseReasonIssue(reason)
  const pause = useMutation({
    ...stokvelContractMutations.pause(),
    toast: "Stokvels paused",
    onSuccess: async () => {
      onOpenChange(false)
      setReason("")
      setTouched(false)
      await invalidateStokvelContract(queryClient)
    },
  })

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) pause.reset()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Pause every stokvel?</AlertDialogTitle>
          <AlertDialogDescription>
            Members can&apos;t pay, and no payouts are released, until you
            resume. Money already paid stays safe in the contract. Creating
            stokvels and starting cycles still work.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Field data-invalid={touched && issue !== null}>
          <FieldLabel htmlFor="pause-reason">Reason</FieldLabel>
          <Textarea
            id="pause-reason"
            value={reason}
            maxLength={PAUSE_REASON_MAX}
            placeholder="e.g. Investigating a failed payout on round 2"
            aria-invalid={touched && issue !== null}
            onChange={(event) => setReason(event.target.value)}
            onBlur={() => setTouched(true)}
          />
          {touched && issue ? (
            <FieldError>{issue}</FieldError>
          ) : (
            <FieldDescription>Recorded in the audit log.</FieldDescription>
          )}
        </Field>
        {pause.isError ? (
          <FieldError>{errorMessage(pause.error)}</FieldError>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pause.isPending}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={pause.isPending}
            onClick={(event) => {
              // Keep the dialog open until the pause has gone through.
              event.preventDefault()
              setTouched(true)
              if (issue === null) pause.mutate({ reason: reason.trim() })
            }}
          >
            {pause.isPending ? "Pausing…" : "Pause all stokvels"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function ResumeDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const resume = useMutation({
    ...stokvelContractMutations.resume(),
    toast: "Stokvels resumed",
    onSuccess: async () => {
      onOpenChange(false)
      await invalidateStokvelContract(queryClient)
    },
  })

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) resume.reset()
      }}
    >
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogTitle>Resume every stokvel?</AlertDialogTitle>
          <AlertDialogDescription>
            Members can pay again, and rounds that are due can be released.
            Resuming releases nothing by itself: a due round goes out with the
            next payment or the scheduled release.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {resume.isError ? (
          <FieldError>{errorMessage(resume.error)}</FieldError>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={resume.isPending}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            disabled={resume.isPending}
            onClick={(event) => {
              event.preventDefault()
              resume.mutate()
            }}
          >
            {resume.isPending ? "Resuming…" : "Resume"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
