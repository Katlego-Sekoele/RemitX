import { BeneficiaryRelationship, PayoutCurrency } from "~/client"
import { Field, FieldDescription, FieldLabel } from "~/components/ui/field"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { relationshipLabel } from "~/lib/beneficiaries"

const RELATIONSHIP_ITEMS = Object.values(BeneficiaryRelationship).map(
  (value) => ({ value, label: relationshipLabel(value) })
)

/** Whether an account's currency is one a beneficiary can be paid out in,
 * so it can pre-fill the payout currency. */
export function asPayoutCurrency(
  currency: string | null | undefined
): PayoutCurrency | null {
  return (Object.values(PayoutCurrency) as string[]).includes(currency ?? "")
    ? (currency as PayoutCurrency)
    : null
}

/** The currencies this person can be paid in: the fiat accounts they
 * already hold, including ZAR. An empty list means they have none yet. */
export function PayoutCurrencyField({
  id,
  value,
  options,
  onChange,
}: {
  id: string
  value: PayoutCurrency | null
  options: readonly PayoutCurrency[]
  onChange: (value: PayoutCurrency) => void
}) {
  if (options.length === 0) {
    return (
      <Field>
        <FieldLabel>Payout currency</FieldLabel>
        <FieldDescription>
          They don&apos;t have a payout account yet. Ask for a reference ending
          in -zar, -usd, -zwl or -nad.
        </FieldDescription>
      </Field>
    )
  }

  const items = options.map((currency) => ({
    value: currency,
    label: currency,
  }))

  return (
    <Field>
      <FieldLabel htmlFor={id}>Payout currency</FieldLabel>
      <Select
        items={items}
        value={value}
        onValueChange={(next) => {
          if (next) onChange(next as PayoutCurrency)
        }}
      >
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="Choose a currency" />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}

export function RelationshipField({
  id,
  value,
  onChange,
}: {
  id: string
  value: BeneficiaryRelationship | null
  onChange: (value: BeneficiaryRelationship) => void
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>Relationship</FieldLabel>
      <Select
        items={RELATIONSHIP_ITEMS}
        value={value}
        onValueChange={(next) => {
          if (next) onChange(next as BeneficiaryRelationship)
        }}
      >
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="How do you know them?" />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {RELATIONSHIP_ITEMS.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}
