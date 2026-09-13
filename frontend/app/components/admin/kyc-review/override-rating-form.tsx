import { WarningIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import {
  errorMessage,
  invalidateApplication,
} from "~/components/admin/kyc-review/format"
import { OptionPicker } from "~/components/admin/kyc-review/option-picker"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import { Field, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { api, type KycApplicationRead, type KycRiskRatingRead } from "~/client"

/**
 * A reviewer's rating, set beside the computed one — never over it. Inline in
 * the Risk card rather than a modal: the reviewer justifies it against the
 * signals and history on the same page, and it can be changed again while the
 * application is pending.
 */
export function OverrideRatingForm({
  application,
  ratings,
  onDone,
}: {
  application: KycApplicationRead
  ratings: readonly KycRiskRatingRead[]
  onDone: () => void
}) {
  const queryClient = useQueryClient()
  const [rating, setRating] = useState("")
  const [reason, setReason] = useState("")

  const override = useMutation({
    ...api.admin.kyc.applications.overrideRiskRating(),
    onSuccess: () => {
      invalidateApplication(queryClient, application.application_id)
      onDone()
    },
  })

  const canSubmit = rating !== "" && reason.trim() !== "" && !override.isPending
  const options = [...ratings]
    .sort((a, b) => b.severity - a.severity)
    .map((row) => ({ value: row.rating, description: row.description }))

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (!canSubmit) return
        override.mutate({
          path: { application_id: application.application_id },
          body: {
            rating,
            reason: reason.trim(),
            expected_version: application.version,
          },
        })
      }}
    >
      <Field>
        <FieldLabel htmlFor="override-rating">New rating</FieldLabel>
        <OptionPicker
          id="override-rating"
          options={options}
          value={rating}
          onChange={setRating}
          placeholder="Select a rating"
          disabled={override.isPending}
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="override-reason">Reason</FieldLabel>
        <Input
          id="override-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Why the computed rating is wrong"
          disabled={override.isPending}
        />
      </Field>
      {override.isError ? (
        <Alert variant="destructive">
          <WarningIcon />
          <AlertTitle>Could not override</AlertTitle>
          <AlertDescription>{errorMessage(override.error)}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" className="flex-1" disabled={!canSubmit}>
          {override.isPending ? "Saving…" : "Save rating"}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
