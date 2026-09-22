import { InfoIcon } from "@phosphor-icons/react"

import { AccountReference } from "~/components/accounts/reference"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import { DEMO_BANK_DETAILS } from "~/lib/accounts"

/**
 * How to fund the ZAR account: an EFT quoting the user's own reference.
 * Inline rather than a modal: it's reference material, read while typing
 * the details into a banking app, and nothing here is a final decision.
 */
export function AddMoneyPanel({ reference }: { reference: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Add money</CardTitle>
        <CardDescription>
          Pay by EFT from your bank, quoting your reference. Deposits are
          matched when RemitX reconciles its bank statement. Your balance
          updates once your deposit is matched.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Alert>
          <InfoIcon />
          <AlertTitle>Demo, no real payments</AlertTitle>
          <AlertDescription>
            These bank details are for the demo only. Don&apos;t send real money
            to them.
          </AlertDescription>
        </Alert>
        <DescriptionList>
          <DescriptionItem>
            <DescriptionTerm>Account name</DescriptionTerm>
            <DescriptionDetails>
              {DEMO_BANK_DETAILS.accountName}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Bank</DescriptionTerm>
            <DescriptionDetails>{DEMO_BANK_DETAILS.bank}</DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Account number</DescriptionTerm>
            <DescriptionDetails>
              {DEMO_BANK_DETAILS.accountNumber}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem>
            <DescriptionTerm>Branch code</DescriptionTerm>
            <DescriptionDetails>
              {DEMO_BANK_DETAILS.branchCode}
            </DescriptionDetails>
          </DescriptionItem>
          <DescriptionItem wide>
            <DescriptionTerm>Your reference</DescriptionTerm>
            <DescriptionDetails>
              <AccountReference reference={reference} />
            </DescriptionDetails>
          </DescriptionItem>
        </DescriptionList>
      </CardContent>
    </Card>
  )
}
