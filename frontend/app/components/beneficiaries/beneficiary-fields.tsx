import { BeneficiaryRelationship, PayoutCurrency } from "~/client"
import { Field, FieldLabel } from "~/components/ui/field"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { relationshipLabel } from "~/lib/beneficiaries"

// Both option lists come from the generated client, which takes them from
// the API's enums — never a list written here.
const PAYOUT_CURRENCY_ITEMS = Object.values(PayoutCurrency).map((value) => ({
  value,
  label: value,
}))

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

export function PayoutCurrencyField({
  id,
  value,
  onChange,
}: {
  id: string
  value: PayoutCurrency | null
  onChange: (value: PayoutCurrency) => void
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>Payout currency</FieldLabel>
      <Select
        items={PAYOUT_CURRENCY_ITEMS}
        value={value}
        onValueChange={(next) => {
          if (next) onChange(next as PayoutCurrency)
        }}
      >
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="Choose a currency" />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {PAYOUT_CURRENCY_ITEMS.map((item) => (
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
