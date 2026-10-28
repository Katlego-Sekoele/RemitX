import { useEffect } from "react"
import { useNavigate, useSearchParams } from "react-router"
import { useMutation } from "@tanstack/react-query"

import { api } from "~/client"
import { Skeleton } from "~/components/ui/skeleton"

export default function TrustMeBankOAuthReturnPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const complete = useMutation(api.trustmebank.trustmebankOauthCallback())

  useEffect(() => {
    const code = params.get("code")
    const state = params.get("state")
    const error = params.get("error")
    if (error) {
      navigate("/app/accounts?trustmebank=denied", { replace: true })
      return
    }
    if (!code || !state || complete.isPending || complete.isSuccess) {
      return
    }
    complete.mutate(
      { body: { code, state } },
      {
        onSettled: () => {
          navigate("/app/accounts?trustmebank=linked", { replace: true })
        },
      }
    )
  }, [params, complete, navigate])

  return (
    <div className="flex flex-col gap-4 p-6">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-96" />
    </div>
  )
}
