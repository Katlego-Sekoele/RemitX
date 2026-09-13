import { ArrowLeftIcon, ShieldWarningIcon } from "@phosphor-icons/react"
import { Link } from "react-router"

import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"

export function ForbiddenPage() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center p-4">
      <Card className="w-full max-w-lg">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-muted">
            <ShieldWarningIcon className="size-6 text-muted-foreground" />
          </div>
          <CardTitle>You do not have access</CardTitle>
          <CardDescription>
            Your roles don&apos;t include this page.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center">
          <Button
            nativeButton={false}
            render={
              <Link to="/">
                <ArrowLeftIcon data-icon="inline-start" />
                Back to RemitX
              </Link>
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}
