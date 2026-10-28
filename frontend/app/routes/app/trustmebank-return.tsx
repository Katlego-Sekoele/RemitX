import { useEffect } from "react"
import { useNavigate, useSearchParams } from "react-router"
import { useMutation } from "@tanstack/react-query"

import { api } from "~/client"
import { Skeleton } from "~/components/ui/skeleton"

export default function TrustMeBankPaymentReturnPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const sync = useMutation(api.trustmebank.trustmebankSyncDeposit())

  useEffect(() => {
    const paymentId = params.get("payment_id")
    if (!paymentId || sync.isPending || sync.isSuccess) {
      return
    }
    sync.mutate(
      { path: { payment_id: paymentId } },
      {
        onSettled: (data) => {
          const status = data?.status ?? params.get("status") ?? "unknown"
          navigate(`/app/accounts?trustmebank=${status.toLowerCase()}`, {
            replace: true,
          })
        },
      }
    )
  }, [params, sync, navigate])

  return (
    <div className="flex flex-col gap-4 p-6">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-96" />
    </div>
  )
}
