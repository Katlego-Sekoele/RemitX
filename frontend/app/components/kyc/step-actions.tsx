import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import { CardFooter } from "~/components/ui/card"

/**
 * Footer of an onboarding step form. Field problems show beside their fields;
 * this alert is for what only the server can say — a format the API refused,
 * a stale version, an upload that failed.
 */
export function StepActions({
  error,
  pending,
  disabled,
  label = "Save and continue",
  pendingLabel = "Saving…",
}: {
  error: string | null
  pending: boolean
  disabled?: boolean
  label?: string
  pendingLabel?: string
}) {
  return (
    <CardFooter className="flex flex-col items-stretch gap-3">
      {error ? (
        <Alert variant="destructive" aria-live="polite">
          <AlertTitle>Could not save</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <Button type="submit" disabled={pending || disabled}>
        {pending ? pendingLabel : label}
      </Button>
    </CardFooter>
  )
}
