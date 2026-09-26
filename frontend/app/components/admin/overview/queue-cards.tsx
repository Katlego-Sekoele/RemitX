import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"

import { api } from "~/client"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { Skeleton } from "~/components/ui/skeleton"
import { useHasPermission } from "~/hooks/use-permissions"
import { PERMISSIONS } from "~/lib/permissions"
import { STUCK_SETTLEMENTS_PATH } from "~/lib/settlement-recovery"

/** Counts that link into the queues a staff member is allowed to open. */
export function QueueCards() {
  const canReadKyc = useHasPermission(PERMISSIONS.kycApplicationRead)
  const canReadDeposits = useHasPermission(PERMISSIONS.cashinRead)
  const canReadBanks = useHasPermission(PERMISSIONS.cashoutRead)
  const canReadOperations = useHasPermission(PERMISSIONS.transactionReadAny)

  const kyc = useQuery({
    ...api.admin.kyc.applications.getQueueCount(),
    enabled: canReadKyc,
  })
  const deposits = useQuery({
    ...api.admin.deposits.getPendingDepositCount(),
    enabled: canReadDeposits,
  })
  const banks = useQuery({
    ...api.admin.bank_accounts.getPendingBankAccountCount(),
    enabled: canReadBanks,
  })
  const operations = useQuery({
    ...api.admin.operations.getOperations(),
    enabled: canReadOperations,
  })

  const cards = [
    canReadKyc
      ? {
          key: "kyc",
          title: "KYC applications",
          description: "Waiting on a reviewer",
          count: kyc.data?.count,
          pending: kyc.isPending,
          href: "/admin/kyc/applications",
          action: "Review",
        }
      : null,
    canReadDeposits
      ? {
          key: "deposits",
          title: "Deposits",
          description: "Waiting to be matched",
          count: deposits.data?.count,
          pending: deposits.isPending,
          href: "/admin/process-deposits",
          action: "Match",
        }
      : null,
    canReadBanks
      ? {
          key: "banks",
          title: "Bank accounts",
          description: "Waiting to be verified",
          count: banks.data?.count,
          pending: banks.isPending,
          href: "/admin/bank-accounts",
          action: "Verify",
        }
      : null,
    canReadOperations
      ? {
          key: "failed",
          title: "Failed settlements",
          description: "Need attention",
          count: operations.data?.failed_settlements,
          pending: operations.isPending,
          href: STUCK_SETTLEMENTS_PATH,
          action: "Review",
        }
      : null,
  ].filter((card) => card !== null)

  if (cards.length === 0) return null

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.key}>
          <CardHeader>
            <CardDescription>{card.title}</CardDescription>
            <CardTitle className="font-heading text-2xl font-semibold tabular-nums">
              {card.pending || card.count === undefined ? (
                <Skeleton className="h-8 w-12" />
              ) : (
                card.count
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">{card.description}</p>
          </CardContent>
          {card.href && card.action ? (
            <CardFooter>
              <Button
                variant="link"
                nativeButton={false}
                render={<Link to={card.href} />}
              >
                {card.action}
              </Button>
            </CardFooter>
          ) : null}
        </Card>
      ))}
    </div>
  )
}
