import { CheckIcon, WarningIcon, XIcon } from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { toast } from "sonner"

import { api, type BankAccountRead } from "~/client"
import { QueryError } from "~/components/accounts/query-error"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { formatDateTime } from "~/components/admin/kyc-review/format"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "~/components/ui/empty"
import { Field, FieldDescription, FieldLabel } from "~/components/ui/field"
import {
  PageHeader,
  PageHeaderDescription,
  PageHeaderTitle,
} from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { Textarea } from "~/components/ui/textarea"
import { errorMessage } from "~/hooks/use-onboarding"
import { useHasPermission } from "~/hooks/use-permissions"
import { PERMISSIONS } from "~/lib/permissions"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/bank-accounts"

// The literal path, not `import.meta.filename` — see routes/admin/access.tsx.
const ROUTE_MODULE = "routes/admin/bank-accounts.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

/**
 * Mirrors how the API gates this queue (routes/admin/bank_accounts.py):
 * reading it needs `cashout:read`, verifying `cashout:approve` and rejecting
 * `cashout:fail` on top. The server decides; this only keeps the UI from
 * offering what it would refuse.
 */
export default function BankAccountVerification() {
  const canRead = useHasPermission(PERMISSIONS.cashoutRead)

  if (!canRead) return <ForbiddenPage />

  return <BankAccountVerificationPage />
}

function BankAccountVerificationPage() {
  const queryClient = useQueryClient()
  const canVerify = useHasPermission(PERMISSIONS.cashoutApprove)
  const canReject = useHasPermission(PERMISSIONS.cashoutFail)
  const pending = useQuery(api.admin.bank_accounts.listPendingBankAccounts())

  const refreshPending = () =>
    queryClient.invalidateQueries({
      queryKey: api.admin.bank_accounts.listPendingBankAccounts().queryKey,
    })

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>{pageRoutingContext?.title}</PageHeaderTitle>
          <PageHeaderDescription>
            Customer bank accounts waiting to be checked before a withdrawal can
            be paid into them. Oldest first.
          </PageHeaderDescription>
        </PageHeader>

        <Card>
          <CardHeader>
            <CardTitle>Awaiting verification</CardTitle>
            <CardDescription>
              Verify an account only once the customer has shown, off platform,
              that it is theirs. A rejection is shown to the customer with your
              reason; they can add the account again once it is fixed.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {pending.isPending ? (
              <Skeleton className="h-40 w-full" />
            ) : pending.isError ? (
              <QueryError
                title="Couldn't load the queue"
                error={pending.error}
                onRetry={() => pending.refetch()}
              />
            ) : pending.data.length === 0 ? (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>Nothing to verify</EmptyTitle>
                  <EmptyDescription>
                    New bank accounts show up here as customers add them.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Added</TableHead>
                    <TableHead>Account holder</TableHead>
                    <TableHead>Bank</TableHead>
                    <TableHead>Account number</TableHead>
                    <TableHead>Branch code</TableHead>
                    <TableHead>Currency</TableHead>
                    {canVerify || canReject ? <TableHead /> : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pending.data.map((account) => (
                    <PendingBankAccountRow
                      key={account.bank_account_id}
                      account={account}
                      canVerify={canVerify}
                      canReject={canReject}
                      onDecided={refreshPending}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </AdminPageFrame>
  )
}

const COLUMNS = 7

/**
 * Deciding happens on the row, like confirming a deposit: the details being
 * checked sit beside the buttons, so neither decision opens a dialog. A
 * rejection's reason is written in a row that opens beneath this one.
 */
function PendingBankAccountRow({
  account,
  canVerify,
  canReject,
  onDecided,
}: {
  account: BankAccountRead
  canVerify: boolean
  canReject: boolean
  onDecided: () => void
}) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState("")
  const holder = account.account_holder_name

  const verify = useMutation({
    ...api.admin.bank_accounts.verifyBankAccount(),
    onSuccess: () => {
      toast.success(`${holder}'s ${account.bank_name} account verified`)
      onDecided()
    },
  })
  const reject = useMutation({
    ...api.admin.bank_accounts.rejectBankAccount(),
    onSuccess: () => {
      toast.success(`${holder}'s ${account.bank_name} account rejected`)
      onDecided()
    },
  })
  const busy = verify.isPending || reject.isPending
  const failed = verify.isError
    ? verify.error
    : reject.isError
      ? reject.error
      : null
  const path = { bank_account_id: account.bank_account_id }

  return (
    <>
      <TableRow>
        <TableCell>{formatDateTime(account.created_at)}</TableCell>
        <TableCell>{holder}</TableCell>
        <TableCell>{account.bank_name}</TableCell>
        <TableCell className="tabular-nums">{account.account_number}</TableCell>
        <TableCell className="tabular-nums">
          {account.branch_code ?? "—"}
        </TableCell>
        <TableCell>{account.currency}</TableCell>
        {canVerify || canReject ? (
          <TableCell>
            <div className="flex justify-end gap-2">
              {canReject ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy || rejecting}
                  onClick={() => setRejecting(true)}
                >
                  <XIcon data-icon="inline-start" />
                  Reject
                </Button>
              ) : null}
              {canVerify ? (
                <Button
                  type="button"
                  size="sm"
                  disabled={busy || rejecting}
                  onClick={() => verify.mutate({ path })}
                >
                  <CheckIcon data-icon="inline-start" />
                  {verify.isPending ? "Verifying…" : "Verify"}
                </Button>
              ) : null}
            </div>
          </TableCell>
        ) : null}
      </TableRow>

      {rejecting ? (
        <TableRow>
          <TableCell colSpan={COLUMNS} className="whitespace-normal">
            <form
              className="flex flex-col gap-3"
              noValidate
              onSubmit={(event) => {
                event.preventDefault()
                if (reason.trim()) {
                  reject.mutate({ path, body: { reason: reason.trim() } })
                }
              }}
            >
              <Field>
                <FieldLabel htmlFor={`reject-${account.bank_account_id}`}>
                  Why is this account being rejected?
                </FieldLabel>
                <Textarea
                  id={`reject-${account.bank_account_id}`}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  disabled={reject.isPending}
                  autoFocus
                />
                <FieldDescription>
                  {holder} sees this on their Bank accounts page. Rejecting is
                  final for this account.
                </FieldDescription>
              </Field>
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={reject.isPending}
                  onClick={() => {
                    setRejecting(false)
                    setReason("")
                    reject.reset()
                  }}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  variant="destructive"
                  disabled={!reason.trim() || reject.isPending}
                >
                  {reject.isPending ? "Rejecting…" : "Reject account"}
                </Button>
              </div>
            </form>
          </TableCell>
        </TableRow>
      ) : null}

      {failed ? (
        <TableRow>
          <TableCell colSpan={COLUMNS} className="whitespace-normal">
            <Alert variant="destructive">
              <WarningIcon />
              <AlertTitle>Couldn&apos;t decide this account</AlertTitle>
              <AlertDescription>{errorMessage(failed)}</AlertDescription>
            </Alert>
          </TableCell>
        </TableRow>
      ) : null}
    </>
  )
}
