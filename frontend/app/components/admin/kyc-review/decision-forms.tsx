import { WarningIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import {
  errorMessage,
  humanise,
  invalidateApplication,
} from "~/components/admin/kyc-review/format"
import { OptionPicker } from "~/components/admin/kyc-review/option-picker"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "~/components/ui/alert-dialog"
import { Button } from "~/components/ui/button"
import { Field, FieldDescription, FieldLabel } from "~/components/ui/field"
import { Textarea } from "~/components/ui/textarea"
import { api, type KycApplicationRead, type KycReasonCodeRead } from "~/client"

/*
 * Modals are kept for the moments that are final and user-initiated —
 * approving, and committing a rejection. Composing a rejection or a request
 * for information happens inline in the panel, because the reviewer is reading
 * the evidence beside it while they write.
 */

// The API's minimum for text an applicant must act on.
const MIN_REASON_LENGTH = 10

// Approval's own code — never a reason to refuse or send back.
const APPROVAL_REASON_CODE = "identity_verified"

type DecisionProps = {
  application: KycApplicationRead
  onDecided: () => void
}

type ComposeProps = DecisionProps & {
  codes: readonly KycReasonCodeRead[]
}

function reasonOptions(codes: readonly KycReasonCodeRead[]) {
  return codes
    .filter((row) => row.reason_code !== APPROVAL_REASON_CODE)
    .map((row) => ({ value: row.reason_code, description: row.description }))
}

export function ApproveButton({ application, onDecided }: DecisionProps) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const approve = useMutation({
    ...api.admin.kyc.applications.approveApplication(),
    onSuccess: () => {
      invalidateApplication(queryClient, application.application_id)
      setOpen(false)
      onDecided()
    },
  })

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) approve.reset()
      }}
    >
      <AlertDialogTrigger render={<Button className="w-full" />}>
        Approve
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Approve this application?</AlertDialogTitle>
          <AlertDialogDescription>
            Grants the verified remittance limits. This can&apos;t be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {approve.isError ? (
          <Alert variant="destructive">
            <WarningIcon />
            <AlertTitle>Could not approve</AlertTitle>
            <AlertDescription>{errorMessage(approve.error)}</AlertDescription>
          </Alert>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <Button
            onClick={() =>
              approve.mutate({
                path: { application_id: application.application_id },
                body: { expected_version: application.version },
              })
            }
            disabled={approve.isPending}
          >
            {approve.isPending ? "Approving…" : "Approve"}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** Reversible — the applicant fixes and resubmits — so no confirmation. */
export function RequestInfoForm({
  application,
  codes,
  onDecided,
}: ComposeProps) {
  const queryClient = useQueryClient()
  const [reasonCode, setReasonCode] = useState("")
  const [reasonText, setReasonText] = useState("")
  const requestInfo = useMutation({
    ...api.admin.kyc.applications.requestApplicationInfo(),
    onSuccess: () => {
      invalidateApplication(queryClient, application.application_id)
      onDecided()
    },
  })
  const canSubmit =
    reasonCode !== "" &&
    reasonText.trim().length >= MIN_REASON_LENGTH &&
    !requestInfo.isPending

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (!canSubmit) return
        requestInfo.mutate({
          path: { application_id: application.application_id },
          body: {
            expected_version: application.version,
            reason_code: reasonCode,
            reason_text: reasonText.trim(),
          },
        })
      }}
    >
      <Field>
        <FieldLabel htmlFor="info-reason">Reason</FieldLabel>
        <OptionPicker
          id="info-reason"
          options={reasonOptions(codes)}
          value={reasonCode}
          onChange={setReasonCode}
          placeholder="Select a reason"
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="info-note">What they must fix</FieldLabel>
        <Textarea
          id="info-note"
          value={reasonText}
          onChange={(event) => setReasonText(event.target.value)}
          placeholder="Please re-upload a clearer photo of your ID."
        />
        <FieldDescription>The applicant sees this.</FieldDescription>
      </Field>
      {requestInfo.isError ? (
        <Alert variant="destructive">
          <WarningIcon />
          <AlertTitle>Could not send back</AlertTitle>
          <AlertDescription>{errorMessage(requestInfo.error)}</AlertDescription>
        </Alert>
      ) : null}
      <Button type="submit" className="w-full" disabled={!canSubmit}>
        {requestInfo.isPending ? "Sending…" : "Send to applicant"}
      </Button>
    </form>
  )
}

/** Composed inline beside the evidence; committed through a confirmation,
 * because a rejection is final. */
export function RejectForm({ application, codes, onDecided }: ComposeProps) {
  const queryClient = useQueryClient()
  const [reasonCode, setReasonCode] = useState("")
  const [note, setNote] = useState("")
  const [confirming, setConfirming] = useState(false)
  const reject = useMutation({
    ...api.admin.kyc.applications.rejectApplication(),
    onSuccess: () => {
      invalidateApplication(queryClient, application.application_id)
      setConfirming(false)
      onDecided()
    },
  })

  return (
    <div className="flex flex-col gap-4">
      <Field>
        <FieldLabel htmlFor="reject-reason">Reason</FieldLabel>
        <OptionPicker
          id="reject-reason"
          options={reasonOptions(codes)}
          value={reasonCode}
          onChange={setReasonCode}
          placeholder="Select a reason"
        />
        <FieldDescription>The applicant sees this.</FieldDescription>
      </Field>
      <Field>
        <FieldLabel htmlFor="reject-note">Internal note</FieldLabel>
        <Textarea
          id="reject-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Staff only"
        />
      </Field>

      <AlertDialog
        open={confirming}
        onOpenChange={(next) => {
          setConfirming(next)
          if (!next) reject.reset()
        }}
      >
        <AlertDialogTrigger
          render={
            <Button
              variant="destructive"
              className="w-full"
              disabled={!reasonCode}
            />
          }
        >
          Reject application
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reject this application?</AlertDialogTitle>
            <AlertDialogDescription>
              <span className="first-letter:uppercase">
                {humanise(reasonCode)}
              </span>
              . This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {reject.isError ? (
            <Alert variant="destructive">
              <WarningIcon />
              <AlertTitle>Could not reject</AlertTitle>
              <AlertDescription>{errorMessage(reject.error)}</AlertDescription>
            </Alert>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              onClick={() =>
                reject.mutate({
                  path: { application_id: application.application_id },
                  body: {
                    expected_version: application.version,
                    reason_code: reasonCode,
                    internal_note: note.trim() || null,
                  },
                })
              }
              disabled={reject.isPending}
            >
              {reject.isPending ? "Rejecting…" : "Reject"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
