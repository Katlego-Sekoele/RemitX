import type { BeneficiaryRead } from "~/client"
import { BeneficiaryAvatar } from "~/components/beneficiaries/beneficiary-avatar"
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "~/components/ui/combobox"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { beneficiaryName } from "~/lib/beneficiaries"

const beneficiaryId = (beneficiary: BeneficiaryRead) =>
  beneficiary.beneficiary_id
const sameBeneficiary = (left: BeneficiaryRead, right: BeneficiaryRead) =>
  left.beneficiary_id === right.beneficiary_id

/**
 * The beneficiary picker used when sending money: a search field whose rows
 * show the person's avatar. Stokvel invite and payout choices use this same
 * control.
 */
export function BeneficiaryCombobox({
  id,
  beneficiaries,
  value,
  onValueChange,
  placeholder = "Choose a beneficiary",
  empty = "No beneficiary matches that.",
  description,
  invalid = false,
}: {
  id: string
  beneficiaries: BeneficiaryRead[]
  value: BeneficiaryRead | null
  onValueChange: (beneficiary: BeneficiaryRead | null) => void
  placeholder?: string
  empty?: string
  description?: (beneficiary: BeneficiaryRead) => string
  invalid?: boolean
}) {
  const describe =
    description ??
    ((beneficiary: BeneficiaryRead) => `Paid in ${beneficiary.payout_currency}`)

  const matches = (beneficiary: BeneficiaryRead, query: string) => {
    const needle = query.trim().toLowerCase()
    return (
      needle === "" ||
      beneficiaryName(beneficiary).toLowerCase().includes(needle) ||
      describe(beneficiary).toLowerCase().includes(needle)
    )
  }

  return (
    <Combobox
      items={beneficiaries}
      value={value}
      onValueChange={onValueChange}
      itemToStringLabel={beneficiaryName}
      itemToStringValue={beneficiaryId}
      isItemEqualToValue={sameBeneficiary}
      filter={matches}
      autoHighlight
    >
      <ComboboxInput
        id={id}
        className="w-full"
        placeholder={placeholder}
        aria-invalid={invalid}
      />
      <ComboboxContent>
        <ComboboxEmpty>{empty}</ComboboxEmpty>
        <ComboboxList>
          {(beneficiary: BeneficiaryRead) => (
            <ComboboxItem key={beneficiary.beneficiary_id} value={beneficiary}>
              <Item size="xs" className="p-0">
                <ItemMedia>
                  <BeneficiaryAvatar beneficiary={beneficiary} size="sm" />
                </ItemMedia>
                <ItemContent>
                  <ItemTitle>{beneficiaryName(beneficiary)}</ItemTitle>
                  <ItemDescription>{describe(beneficiary)}</ItemDescription>
                </ItemContent>
              </Item>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
