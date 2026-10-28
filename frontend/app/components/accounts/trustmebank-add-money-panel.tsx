import { useMutation, useQuery } from "@tanstack/react-query"
import { BankIcon, InfoIcon } from "@phosphor-icons/react"
import { useState } from "react"

import { api } from "~/client"
import { AccountReference } from "~/components/accounts/reference"
import { DEMO_BANK_DETAILS } from "~/lib/accounts"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { Input } from "~/components/ui/input"
import { Label } from "~/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"

type Props = {
  reference: string
  verified: boolean
}

export function TrustMeBankAddMoneyPanel({ reference, verified }: Props) {
  const status = useQuery(api.trustmebank.trustmebankStatus())
  const link = useQuery({
    ...api.trustmebank.trustmebankLink(),
    enabled: status.data?.enabled === true,
  })
  const accounts = useQuery({
    ...api.trustmebank.trustmebankAccounts(),
    enabled: link.data?.linked === true,
  })
  const connect = useMutation(api.trustmebank.trustmebankConnect())
  const startDeposit = useMutation(api.trustmebank.trustmebankStartDeposit())

  const [amount, setAmount] = useState("100.00")
  const [debtorAccountId, setDebtorAccountId] = useState<string>("")

  if (status.isPending) {
    return null
  }
  if (!status.data?.enabled) {
    return <LegacyEftPanel reference={reference} />
  }

  const onConnect = () => {
    connect.mutate({}, {
      onSuccess: (data) => {
        window.location.href = data.authorize_url
      },
    })
  }

  const onDeposit = () => {
    if (!debtorAccountId) {
      return
    }
    startDeposit.mutate(
      {
        body: {
          amount,
          debtor_account_id: debtorAccountId,
        },
      },
      {
        onSuccess: (data) => {
          window.location.href = data.authorisation_url
        },
      }
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add money</CardTitle>
        <CardDescription>
          Pay through TrustMeBank with Open Banking authorisation, or use EFT
          reconciliation below.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Alert>
          <InfoIcon />
          <AlertTitle>Demo bank</AlertTitle>
          <AlertDescription>
            TrustMeBank is a course mock. Use seeded customers such as{" "}
            alice@example.com / alice123 when authorising.
          </AlertDescription>
        </Alert>

        {!verified ? (
          <p className="text-muted-foreground text-sm">
            Complete verification before adding money through TrustMeBank.
          </p>
        ) : link.data?.linked === false ? (
          <Button type="button" onClick={onConnect} disabled={connect.isPending}>
            <BankIcon />
            Connect TrustMeBank
          </Button>
        ) : (
          <div className="flex flex-col gap-3">
            {link.data?.customer_name ? (
              <p className="text-sm">
                Connected as{" "}
                <span className="font-medium">{link.data.customer_name}</span>
              </p>
            ) : null}
            <div className="grid gap-2">
              <Label htmlFor="tmb-amount">Amount (ZAR)</Label>
              <Input
                id="tmb-amount"
                inputMode="decimal"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="tmb-account">Pay from</Label>
              <Select
                value={debtorAccountId}
                onValueChange={(value) => setDebtorAccountId(value ?? "")}
              >
                <SelectTrigger id="tmb-account">
                  <SelectValue placeholder="Choose a bank account" />
                </SelectTrigger>
                <SelectContent>
                  {(accounts.data ?? []).map((account) => (
                    <SelectItem key={account.id} value={account.id}>
                      {account.name} ({account.account_number})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              type="button"
              onClick={onDeposit}
              disabled={startDeposit.isPending || !debtorAccountId}
            >
              Authorise payment in TrustMeBank
            </Button>
          </div>
        )}

        <div className="border-t pt-4">
          <p className="text-muted-foreground mb-3 text-sm font-medium">
            Or pay by EFT (statement reconciliation)
          </p>
          <LegacyEftPanel reference={reference} embedded />
        </div>
      </CardContent>
    </Card>
  )
}

function LegacyEftPanel({
  reference,
  embedded = false,
}: {
  reference: string
  embedded?: boolean
}) {
  const body = (
    <>
      {!embedded ? (
        <CardHeader>
          <CardTitle>Add money</CardTitle>
          <CardDescription>
            Pay by EFT from your bank, quoting your reference. Deposits are
            matched when RemitX reconciles its bank statement.
          </CardDescription>
        </CardHeader>
      ) : null}
      <CardContent className={embedded ? "p-0" : undefined}>
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>Account name</DescriptionTerm>
            <DescriptionDetails>
              {DEMO_BANK_DETAILS.accountName}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Your reference</DescriptionTerm>
            <DescriptionDetails>
              <AccountReference reference={reference} />
            </DescriptionDetails>
          </DescriptionItem>
        </DescriptionList>
      </CardContent>
    </>
  )
  if (embedded) {
    return body
  }
  return <Card>{body}</Card>
}
