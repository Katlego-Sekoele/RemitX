import {
  DownloadSimpleIcon,
  FileCsvIcon,
  PlusIcon,
  TrashIcon,
  WarningIcon,
} from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { Fragment, useState } from "react"
import { Link } from "react-router"

import { AccountReferenceCombobox } from "~/components/admin/account-reference-combobox"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
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
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import { DatePicker } from "~/components/ui/date-picker"
import { Input } from "~/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { api, PayoutCurrency } from "~/client"
import { useHasPermission } from "~/hooks/use-permissions"
import {
  STATEMENT_COLUMNS,
  mismatchedAccountCurrency,
  statementToCsv,
  type StatementColumn,
  type StatementLine,
} from "~/lib/bank-statement-csv"
import { PERMISSIONS } from "~/lib/permissions"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/statement-csv"

// The literal path, not `import.meta.filename` — see routes/admin/access.tsx.
const ROUTE_MODULE = "routes/admin/statement-csv.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

type DraftLine = StatementLine & { id: string }

const COLUMN_LABEL: Record<StatementColumn, string> = {
  date: "Date",
  description: "Description",
  reference: "Reference",
  amount: "Amount",
  currency: "Currency",
}

// RemitX has a bank account in every payout currency, so a statement line
// can be in any of them.
const CURRENCY_ITEMS = Object.values(PayoutCurrency).map((value) => ({
  value,
  label: value,
}))

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

function blankLine(): DraftLine {
  return {
    id: crypto.randomUUID(),
    date: "",
    description: "",
    reference: "",
    amount: "",
    currency: PayoutCurrency.ZAR,
  }
}

/**
 * Bank statement CSV builder for the cash-in job. Same gate as Process deposits
 * (`cashin:read`): building the statement is part of that flow, and staff
 * without the cash-in role never see it. The server still refuses the
 * upload that actually moves money.
 */
export default function StatementCsv() {
  const canRead = useHasPermission(PERMISSIONS.cashinRead)

  if (!canRead) return <ForbiddenPage />

  return <StatementCsvPage />
}

function StatementCsvPage() {
  const [lines, setLines] = useState<DraftLine[]>([])
  const accounts = useQuery(api.admin.deposits.listAccountReferences())
  const accountList = accounts.data ?? []
  const mismatchOf = (line: DraftLine) =>
    mismatchedAccountCurrency(line, accountList)
  const hasMismatch = lines.some((line) => mismatchOf(line) !== null)

  function update(id: string, column: StatementColumn, value: string) {
    setLines((current) =>
      current.map((line) =>
        line.id === id ? { ...line, [column]: value } : line
      )
    )
  }

  function download() {
    const csv = statementToCsv(lines)
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }))
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = "bank-statement.csv"
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          {pageRoutingContext?.title}
        </h1>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            nativeButton={false}
            render={
              <Link to="/admin/process-deposits">
                <FileCsvIcon data-icon="inline-start" />
                Process deposits
              </Link>
            }
          />
          <Button
            onClick={download}
            disabled={lines.length === 0 || hasMismatch}
          >
            <DownloadSimpleIcon data-icon="inline-start" />
            Download CSV
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Bank statement</CardTitle>
          <CardDescription>
            Date, description, reference, amount, and currency. The currency is
            that of the RemitX bank account the money came into, and must match
            the account the reference names. A reference such as sipho1-zar is
            what matching uses; a negative amount is outgoing and skipped.
            Upload the file on Process deposits.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {lines.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <FileCsvIcon />
                </EmptyMedia>
                <EmptyTitle>No lines</EmptyTitle>
                <EmptyDescription>
                  Add a line to build a bank statement CSV for upload.
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button
                  variant="outline"
                  onClick={() =>
                    setLines((current) => [...current, blankLine()])
                  }
                >
                  <PlusIcon data-icon="inline-start" />
                  Add line
                </Button>
              </EmptyContent>
            </Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {STATEMENT_COLUMNS.map((column) => (
                    <TableHead key={column}>{COLUMN_LABEL[column]}</TableHead>
                  ))}
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {lines.map((line, index) => {
                  const mismatch = mismatchOf(line)
                  return (
                    <Fragment key={line.id}>
                      <TableRow>
                        {STATEMENT_COLUMNS.map((column) => (
                          <TableCell key={column}>
                            {column === "reference" ? (
                              <AccountReferenceCombobox
                                accounts={accountList}
                                value={line.reference}
                                onChange={(reference) =>
                                  update(line.id, "reference", reference)
                                }
                                placeholder={`Reference on line ${index + 1}`}
                              />
                            ) : column === "date" ? (
                              <DatePicker
                                id={`${line.id}-date`}
                                value={line.date}
                                onChange={(value) =>
                                  update(line.id, "date", value)
                                }
                              />
                            ) : column === "currency" ? (
                              <Select
                                items={CURRENCY_ITEMS}
                                value={line.currency}
                                onValueChange={(next) => {
                                  if (next) update(line.id, "currency", next)
                                }}
                              >
                                <SelectTrigger
                                  className="w-full"
                                  aria-label={`Currency on line ${index + 1}`}
                                >
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent alignItemWithTrigger={false}>
                                  {CURRENCY_ITEMS.map((item) => (
                                    <SelectItem
                                      key={item.value}
                                      value={item.value}
                                    >
                                      {item.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <Input
                                value={line[column]}
                                inputMode={
                                  column === "amount" ? "decimal" : undefined
                                }
                                aria-label={`${COLUMN_LABEL[column]} on line ${index + 1}`}
                                onChange={(event) =>
                                  update(line.id, column, event.target.value)
                                }
                              />
                            )}
                          </TableCell>
                        ))}
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label={`Remove line ${index + 1}`}
                            onClick={() =>
                              setLines((current) =>
                                current.filter((item) => item.id !== line.id)
                              )
                            }
                          >
                            <TrashIcon />
                          </Button>
                        </TableCell>
                      </TableRow>
                      {mismatch && (
                        <TableRow>
                          <TableCell
                            colSpan={STATEMENT_COLUMNS.length + 1}
                            className="whitespace-normal"
                          >
                            <Alert variant="destructive">
                              <WarningIcon />
                              <AlertTitle>
                                Line {index + 1}: currency doesn&apos;t match
                                the account
                              </AlertTitle>
                              <AlertDescription>
                                {line.reference.trim()} is a {mismatch} account,
                                but this line is in {line.currency}. Change the
                                currency, or use the customer&apos;s{" "}
                                {line.currency} reference.
                              </AlertDescription>
                            </Alert>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          )}
          <div>
            <Button
              variant="outline"
              onClick={() => setLines((current) => [...current, blankLine()])}
            >
              <PlusIcon data-icon="inline-start" />
              Add line
            </Button>
          </div>
        </CardContent>
      </Card>
    </AdminPageFrame>
  )
}
