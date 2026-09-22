import { WarningIcon } from "@phosphor-icons/react"

import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "~/components/ui/alert"
import { Button } from "~/components/ui/button"

type QueryErrorProps = {
  title: string
  error: unknown
  onRetry: () => void
}

/** A failed load, with the API's own message and a way to try again. */
export function QueryError({ title, error, onRetry }: QueryErrorProps) {
  return (
    <Alert variant="destructive">
      <WarningIcon />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        {error instanceof Error ? error.message : "Something went wrong."}
      </AlertDescription>
      <AlertAction>
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </AlertAction>
    </Alert>
  )
}
