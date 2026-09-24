import {
  DownloadSimpleIcon,
  FileCsvIcon,
  PlusIcon,
  TrashIcon,
} from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router"

import { AccountReferenceCombobox } from "~/components/admin/account-reference-combobox"
import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
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
import { Input } from "~/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { api } from "~/client"
import { useHasPermission } from "~/hooks/use-permissions"
import {
  STATEMENT_COLUMNS,
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
}

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
          <Button onClick={download} disabled={lines.length === 0}>
            <DownloadSimpleIcon data-icon="inline-start" />
            Download CSV
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Bank statement</CardTitle>
          <CardDescription>
            Date, description, reference, and amount. A reference such as
            sipho1-zar is what matching uses; a negative amount is outgoing and
            skipped. Upload the file on Process deposits.
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
                {lines.map((line, index) => (
                  <TableRow key={line.id}>
                    {STATEMENT_COLUMNS.map((column) => (
                      <TableCell key={column}>
                        {column === "reference" ? (
                          <AccountReferenceCombobox
                            accounts={accounts.data ?? []}
                            value={line.reference}
                            onChange={(reference) =>
                              update(line.id, "reference", reference)
                            }
                            placeholder={`Reference on line ${index + 1}`}
                          />
                        ) : (
                          <Input
                            value={line[column]}
                            type={column === "date" ? "date" : "text"}
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
                ))}
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
