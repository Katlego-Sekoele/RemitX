import { Link } from "react-router"

import type { InFlightTransferRead } from "~/client"
import { TransferStatusBadge } from "~/components/transfers/transfer-status-badge"
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
import { formatMoney } from "~/lib/money"
import { formatWhen, transferPath } from "~/lib/transfers"

/** Transfers still queued or settling. */
export function InFlightTransfers({
  transfers,
}: {
  transfers: InFlightTransferRead[]
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>In progress</CardTitle>
        <CardDescription>
          Transfers that are queued or still settling.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Transfer</TableHead>
              <TableHead>Amount</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {transfers.map((transfer) => {
              const who = transfer.counterparty_name ?? "Unnamed"
              return (
                <TableRow key={transfer.remittance_id}>
                  <TableCell>
                    <Button
                      variant="link"
                      size="sm"
                      nativeButton={false}
                      render={
                        <Link to={transferPath(transfer.remittance_id)} />
                      }
                    >
                      {transfer.direction === "sent"
                        ? `To ${who}`
                        : `From ${who}`}
                    </Button>
                  </TableCell>
                  <TableCell>
                    {transfer.direction === "sent" ? "−" : "+"}
                    {formatMoney(transfer.amount, transfer.currency)}
                  </TableCell>
                  <TableCell>
                    <TransferStatusBadge status={transfer.status} />
                  </TableCell>
                  <TableCell>{formatWhen(transfer.created_at)}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
