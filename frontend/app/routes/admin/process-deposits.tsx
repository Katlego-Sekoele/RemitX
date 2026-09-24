import {
  CheckCircleIcon,
  FileCsvIcon,
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
  type AccountReferenceRead,
  type DepositRow,
  type PendingDepositRead as PendingDeposit,
  type SkippedStatementLineRead,
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
            Statement lines that didn&apos;t match an account. Search the
            customer on the row and confirm; the credit lands on the account
            you pick (ZAR or token). Only confirm once they have proven, off
            platform, that the payment is theirs.
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
  const [skippedLines, setSkippedLines] = useState<SkippedStatementLineRead[]>(
    []
  )

  const process = useMutation({
    ...api.admin.deposits.processDeposits(),
    onSuccess: (data) => {
      onProcessed()
      setSkippedLines(data.skipped ?? [])
      setCompleted(true)
      const needsFix = (data.skipped ?? []).some(
        (line) => line.reason === "unparseable_date"
      )
      if (!needsFix) {
        setFile(null)
        setRows([])
      }
    },
  })

  function clearFile() {
    setFile(null)
    setRows([])
    setParseError(null)
    setCompleted(false)
    setSkippedLines([])
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
            {skippedLines.length > 0 && (
              <AlertDescription>
                {skippedLines.length} line
                {skippedLines.length === 1 ? "" : "s"} were not imported. See
                below to fix and run again.
              </AlertDescription>
            )}
          </Alert>
        )}

        {skippedLines.length > 0 && (
          <Alert variant="destructive">
            <WarningIcon />
            <AlertTitle>Lines not imported</AlertTitle>
            <AlertDescription>
              <ul className="mt-2 list-disc space-y-2 pl-5">
                {skippedLines.map((line, index) => (
                  <li key={`${line.reference ?? "line"}-${index}`}>
                    <span className="font-medium">
                      {line.reference ?? "—"} · {line.amount}
                      {line.date ? ` · ${line.date}` : ""}
                    </span>
                    <span className="block text-sm">{line.message}</span>
                  </li>
                ))}
              </ul>
            </AlertDescription>
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
  const accounts = useQuery({
    ...api.admin.deposits.listAccountReferences(),
    enabled: canConfirm,
  })

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
          {canConfirm && <TableHead>Account</TableHead>}
          {canConfirm && <TableHead />}
        </TableRow>
      </TableHeader>
      <TableBody>
        {deposits.map((deposit) =>
          canConfirm ? (
            <PendingDepositRow
              key={deposit.deposit_id}
              deposit={deposit}
              accounts={accounts.data ?? []}
              onResolved={onResolved}
            />
          ) : (
            <TableRow key={deposit.deposit_id}>
              <TableCell>{formatDate(deposit.created_at)}</TableCell>
              <TableCell>
                {deposit.amount} {deposit.currency}
              </TableCell>
              <TableCell>{deposit.reference ?? "—"}</TableCell>
            </TableRow>
          )
        )}
      </TableBody>
    </Table>
  )
}

/**
 * Matching a pending line happens on the row. The amount and the statement
 * reference are already beside the account search, so confirming does not
 * open a dialog.
 */
function PendingDepositRow({
  deposit,
  accounts,
  onResolved,
}: {
  deposit: PendingDeposit
  accounts: AccountReferenceRead[]
  onResolved: () => void
}) {
  const [accountReference, setAccountReference] = useState("")

  const approve = useMutation({
    ...api.admin.deposits.approveDeposit(),
    onSuccess: () => {
      setAccountReference("")
      onResolved()
    },
  })

  return (
    <>
      <TableRow>
        <TableCell>{formatDate(deposit.created_at)}</TableCell>
        <TableCell>
          {deposit.amount} {deposit.currency}
        </TableCell>
        <TableCell>{deposit.reference ?? "—"}</TableCell>
        <TableCell className="min-w-64">
          <AccountReferenceCombobox
            accounts={accounts}
            value={accountReference}
            onChange={setAccountReference}
            disabled={approve.isPending}
            placeholder="Search accounts"
          />
        </TableCell>
        <TableCell>
          <Button
            type="button"
            size="sm"
            disabled={!accountReference.trim() || approve.isPending}
            onClick={() =>
              approve.mutate({
                path: { deposit_id: deposit.deposit_id },
                body: { account_reference: accountReference.trim() },
              })
            }
          >
            {approve.isPending ? "Confirming…" : "Confirm"}
          </Button>
        </TableCell>
      </TableRow>
      {approve.isError && (
        <TableRow>
          <TableCell colSpan={5} className="whitespace-normal">
            <Alert variant="destructive">
              <WarningIcon />
              <AlertTitle>Could not confirm</AlertTitle>
              <AlertDescription>{errorMessage(approve.error)}</AlertDescription>
            </Alert>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}
