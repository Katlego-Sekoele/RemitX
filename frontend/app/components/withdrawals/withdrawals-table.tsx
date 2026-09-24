import type { BankAccountRead, WithdrawalRead } from "~/client"
import { Badge } from "~/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { formatMoney } from "~/lib/money"
import { formatWhen } from "~/lib/transfers"
import { bankAccountLabel, withdrawalStatus } from "~/lib/withdrawals"

/** Past withdrawals, newest first as the API returns them. `bankAccounts`
 * names each destination; one it doesn't know is shown as "Bank account". */
export function WithdrawalsTable({
  withdrawals,
  bankAccounts,
}: {
  withdrawals: readonly WithdrawalRead[]
  bankAccounts: readonly BankAccountRead[]
}) {
  const names = new Map(
    bankAccounts.map((account) => [
      account.bank_account_id,
      bankAccountLabel(account),
    ])
  )

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>To</TableHead>
          <TableHead className="text-right">Withdrawn</TableHead>
          <TableHead className="text-right">Fee</TableHead>
          <TableHead className="text-right">Paid out</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Date</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {withdrawals.map((withdrawal) => {
          const status = withdrawalStatus(withdrawal.status)
          const money = (amount: string) =>
            formatMoney(amount, withdrawal.currency)
          return (
            <TableRow key={withdrawal.withdrawal_id}>
              <TableCell>
                {names.get(withdrawal.bank_account_id) ?? "Bank account"}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {money(withdrawal.gross_amount)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {money(withdrawal.fee_amount)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {money(withdrawal.net_amount)}
              </TableCell>
              <TableCell>
                <Badge variant={status.variant}>{status.label}</Badge>
              </TableCell>
              <TableCell>{formatWhen(withdrawal.created_at)}</TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
