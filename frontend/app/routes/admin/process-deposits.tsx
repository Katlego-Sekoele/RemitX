import {
  CheckCircleIcon,
  FileCsvIcon,
  PencilSimpleIcon,
  TrashIcon,
  UploadSimpleIcon,
  WarningIcon,
} from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useId, useState } from "react"
import { Link } from "react-router"

import { AccountReferenceCombobox } from "~/components/admin/account-reference-combobox"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import {
  Attachment,
  AttachmentAction,
  AttachmentActions,
  AttachmentContent,
  AttachmentDescription,
  AttachmentMedia,
  AttachmentTitle,
} from "~/components/ui/attachment"
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog"
import { Label } from "~/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import type { Route } from "./+types/process-deposits"
import { useHasPermission } from "~/hooks/use-permissions"
import {
  api,
  type DepositRow,
  type PendingDepositRead as PendingDeposit,
} from "~/client"
import {
  missingStatementColumns,
  parseStatementCsv,
  type CsvRow,
} from "~/lib/bank-statement-csv"
import { PERMISSIONS } from "~/lib/permissions"
import { adminRouteContext } from "~/routes/admin/admin.routes"

const moduleName = import.meta.filename
const pageRoutingContextByModuleName = adminRouteContext(moduleName)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContextByModuleName?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

/** Statement rows only ever carry reference/amount/date to `process_deposits`
 * — everything else in the CSV (description, ...) is for the admin's eyes
 * only. */
function toDepositRows(rows: CsvRow[]): DepositRow[] {
  return rows.map((row) => ({
    reference: row.reference?.trim() ? row.reference.trim() : null,
    amount: row.amount ?? "0",
    date: row.date?.trim() ? row.date.trim() : null,
  }))
}

/**
 * Mirrors how the API gates this page (routes/admin/deposits.py), and the
 * same gate as Statement CSV: reading the queue needs `cashin:read`, and the
 * two ways to move money against it need `cashin:confirm` on top. Staff
 * without the cash-in role get neither page. The server decides; this only
 * keeps the UI from offering what it would refuse.
 */
export default function ProcessDeposits() {
  const canRead = useHasPermission(PERMISSIONS.cashinRead)

  if (!canRead) return <ForbiddenPage />

  return <ProcessDepositsPage />
}

function ProcessDepositsPage() {
  const queryClient = useQueryClient()
  const canConfirm = useHasPermission(PERMISSIONS.cashinConfirm)

  const pending = useQuery(api.admin.deposits.listPendingDeposits())

  const refreshPending = () =>
    queryClient.invalidateQueries({
      queryKey: api.admin.deposits.listPendingDeposits().queryKey,
    })

  return (
    <AdminPageFrame module={moduleName}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-2">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">
            {pageRoutingContextByModuleName?.title}
          </h1>
        </div>
        <Button
          variant="outline"
          nativeButton={false}
          render={
            <Link to="/admin/statement-csv">
              <FileCsvIcon data-icon="inline-start" />
              Statement CSV
            </Link>
          }
        />
      </div>

      {canConfirm && <StatementUpload onProcessed={refreshPending} />}

      <Card>
        <CardHeader>
          <CardTitle>Pending deposits</CardTitle>
          <CardDescription>
            Statement lines that didn&apos;t match an account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PendingTable
            deposits={pending.data}
            loading={pending.isPending}
            error={pending.isError ? pending.error : null}
            onResolved={refreshPending}
            canConfirm={canConfirm}
          />
        </CardContent>
      </Card>
    </AdminPageFrame>
  )
}

/**
 * Choosing the file is not final — a bad CSV can be removed — so it stays
 * on the page, in the same drop zone KYC uploads use. Running the statement
 * is the action, and it sits beside the file rather than inside a modal.
 */
function StatementUpload({ onProcessed }: { onProcessed: () => void }) {
  const inputId = useId()
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [rows, setRows] = useState<CsvRow[]>([])
  const [parseError, setParseError] = useState<string | null>(null)
  const [completed, setCompleted] = useState(false)

  const process = useMutation({
    ...api.admin.deposits.processDeposits(),
    onSuccess: () => {
      onProcessed()
      setCompleted(true)
      setFile(null)
      setRows([])
    },
  })

  function clearFile() {
    setFile(null)
    setRows([])
    setParseError(null)
    setCompleted(false)
    process.reset()
  }

  async function handleFile(selected: File | undefined) {
    if (!selected || process.isPending) return
    setCompleted(false)
    try {
      const text = await selected.text()
      const parsed = parseStatementCsv(text)
      if (missingStatementColumns(parsed.headers).length > 0) {
        setParseError('CSV must have "reference" and "amount" columns.')
        setFile(null)
        setRows([])
        return
      }
      setParseError(null)
      setFile(selected)
      setRows(parsed.rows)
    } catch {
      setParseError("Could not read that file as text.")
      setFile(null)
      setRows([])
    }
  }

  const canRun = file !== null && rows.length > 0 && !parseError

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bank statement</CardTitle>
        <CardDescription>
          Drop the CSV from Statement CSV. Matching lines credit the customer.
          The rest wait below.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {completed && (
          <Alert>
            <CheckCircleIcon />
            <AlertTitle>Simulation completed</AlertTitle>
          </Alert>
        )}

        {file ? (
          <Attachment
            className="w-full max-w-full"
            state={process.isPending ? "processing" : "done"}
          >
            <AttachmentMedia variant="icon">
              <FileCsvIcon />
            </AttachmentMedia>
            <AttachmentContent>
              <AttachmentTitle>{file.name}</AttachmentTitle>
              <AttachmentDescription>
                {rows.length} line{rows.length === 1 ? "" : "s"}
              </AttachmentDescription>
            </AttachmentContent>
            <AttachmentActions>
              <AttachmentAction
                aria-label="Remove file"
                disabled={process.isPending}
                onClick={clearFile}
              >
                <TrashIcon />
              </AttachmentAction>
            </AttachmentActions>
          </Attachment>
        ) : (
          <Attachment
            state={parseError ? "error" : "idle"}
            data-dragging={dragging}
            aria-disabled={process.isPending}
            className="min-h-24 w-full max-w-full justify-center"
          >
            <input
              id={inputId}
              type="file"
              accept=".csv,text/csv"
              disabled={process.isPending}
              aria-label="Bank statement CSV"
              className="absolute inset-0 cursor-pointer opacity-0 disabled:cursor-not-allowed"
              onDragEnter={() => setDragging(true)}
              onDragLeave={() => setDragging(false)}
              onDrop={() => setDragging(false)}
              onChange={(event) => {
                handleFile(event.target.files?.[0])
                event.target.value = ""
              }}
            />
            <AttachmentMedia variant="icon">
              <UploadSimpleIcon aria-hidden="true" />
            </AttachmentMedia>
            <AttachmentContent>
              <AttachmentTitle>
                Drop a statement here, or click to browse
              </AttachmentTitle>
              <AttachmentDescription>
                CSV with reference and amount columns.
              </AttachmentDescription>
            </AttachmentContent>
          </Attachment>
        )}

        {parseError && (
          <Alert variant="destructive">
            <WarningIcon />
            <AlertTitle>Could not use that file</AlertTitle>
            <AlertDescription>{parseError}</AlertDescription>
          </Alert>
        )}

        {process.isError && (
          <Alert variant="destructive">
            <WarningIcon />
            <AlertTitle>Simulation failed</AlertTitle>
            <AlertDescription>{errorMessage(process.error)}</AlertDescription>
          </Alert>
        )}

        <div>
          <Button
            type="button"
            onClick={() =>
              process.mutate({ body: { rows: toDepositRows(rows) } })
            }
            disabled={!canRun || process.isPending}
          >
            {process.isPending ? "Running…" : "Run Process Deposit Simulation"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function PendingTable({
  deposits,
  loading,
  error,
  onResolved,
  canConfirm,
}: {
  deposits: PendingDeposit[] | undefined
  loading: boolean
  error: unknown
  onResolved: () => void
  canConfirm: boolean
}) {
  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <WarningIcon />
        <AlertTitle>Could not load pending deposits</AlertTitle>
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    )
  }

  if (!deposits || deposits.length === 0) {
    return <p className="text-sm text-muted-foreground">No pending deposits.</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Reference</TableHead>
          <TableHead className="w-8" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {deposits.map((deposit) => (
          <TableRow key={deposit.deposit_id}>
            <TableCell>{formatDate(deposit.created_at)}</TableCell>
            <TableCell>
              {deposit.amount} {deposit.currency}
            </TableCell>
            <TableCell>{deposit.reference ?? "—"}</TableCell>
            <TableCell>
              {canConfirm && (
                <ApproveDialog deposit={deposit} onResolved={onResolved} />
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function ApproveDialog({
  deposit,
  onResolved,
}: {
  deposit: PendingDeposit
  onResolved: () => void
}) {
  const [open, setOpen] = useState(false)
  const [accountReference, setAccountReference] = useState("")
  const accounts = useQuery({
    ...api.admin.deposits.listAccountReferences(),
    enabled: open,
  })

  const approve = useMutation({
    ...api.admin.deposits.approveDeposit(),
    onSuccess: () => {
      onResolved()
      setOpen(false)
    },
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setAccountReference("")
          approve.reset()
        }
      }}
    >
      <DialogTrigger render={<Button variant="ghost" size="icon-xs" />}>
        <PencilSimpleIcon />
        <span className="sr-only">Resolve deposit</span>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm deposit</DialogTitle>
          <DialogDescription>
            {deposit.amount} {deposit.currency} — statement reference &quot;
            {deposit.reference ?? "none"}&quot;. Credit lands on that
            customer&apos;s ZAR account. Only confirm once they have proven, off
            platform, that the payment is theirs.
          </DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (accountReference.trim()) {
              approve.mutate({
                path: { deposit_id: deposit.deposit_id },
                body: { account_reference: accountReference.trim() },
              })
            }
          }}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="deposit-account-reference">Account reference</Label>
            <AccountReferenceCombobox
              id="deposit-account-reference"
              accounts={accounts.data ?? []}
              value={accountReference}
              onChange={setAccountReference}
              disabled={approve.isPending}
              placeholder="Search accounts"
            />
          </div>

          {approve.isError && (
            <Alert variant="destructive">
              <WarningIcon />
              <AlertTitle>Could not confirm</AlertTitle>
              <AlertDescription>{errorMessage(approve.error)}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button
              type="submit"
              disabled={!accountReference.trim() || approve.isPending}
            >
              {approve.isPending ? "Confirming…" : "Confirm deposit"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
