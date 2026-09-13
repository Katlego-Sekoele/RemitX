import { useAuth } from "@clerk/react-router"

import { api } from "~/client"
import { useClerkMounted } from "~/components/clerk-mounted"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { useMePermissions } from "~/hooks/use-permissions"
import { pathForStep } from "~/lib/kyc-onboarding"

/**
 * Signed-in prompt on the home page. Does not force a redirect — a deep link
 * to profile or beneficiaries (when those exist) must still work without an
 * approved application.
 */
export function VerificationCard() {
  const clerkMounted = useClerkMounted()
  if (!clerkMounted) return null

  return <SignedInVerificationCard />
}

function SignedInVerificationCard() {
  const { isSignedIn } = useAuth()
  const access = useMePermissions()
  const isAdmin = access.data?.is_admin === true
  const isCustomer = Boolean(isSignedIn) && access.isSuccess && !isAdmin
  const query = useQuery({
    ...api.kyc.onboarding.getApplication(),
    enabled: isCustomer,
  })
  const standing = query.data?.standing.status
  if (!isCustomer) return null
  if (standing === "approved" || standing === "review_due") return null
  if (!query.data) return null

  const next = pathForStep(query.data.next_step)

  return (
    <div>
      <div className="mx-auto w-full max-w-6xl px-6 py-6">
        <Card>
          <CardHeader>
            <CardTitle>Complete your verification</CardTitle>
            <CardDescription>
              Verify your identity to start sending.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button nativeButton={false} render={<Link to={next} />}>
              Continue verification
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
