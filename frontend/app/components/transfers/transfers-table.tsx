import { Link } from "react-router"

import type { TransferRead as Transfer } from "~/client"
import { TransferStatusBadge } from "~/components/transfers/transfer-status-badge"
import { Button } from "~/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { formatMoney } from "~/lib/money"
import { formatWhen, headlineAmount, transferPath } from "~/lib/transfers"

/** Sent and received transfers, each linking to its own page. */
export function TransfersTable({ transfers }: { transfers: Transfer[] }) {
  return (
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
          const { amount, currency } = headlineAmount(transfer)
          const who = transfer.counterparty_name ?? "Unnamed"
          return (
            <TableRow key={transfer.remittance_id}>
              <TableCell>
                <Button
                  variant="link"
                  size="sm"
                  nativeButton={false}
                  render={<Link to={transferPath(transfer.remittance_id)} />}
                >
                  {transfer.direction === "sent" ? `To ${who}` : `From ${who}`}
                </Button>
              </TableCell>
              <TableCell>
                {transfer.direction === "sent" ? "−" : "+"}
                {formatMoney(amount, currency)}
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
  )
}
