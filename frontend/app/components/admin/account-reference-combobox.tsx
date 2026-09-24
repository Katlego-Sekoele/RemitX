import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "~/components/ui/combobox"
import type { AccountReferenceRead } from "~/client"

const labelOf = (account: AccountReferenceRead) => account.reference
const sameReference = (
  left: AccountReferenceRead,
  right: AccountReferenceRead
) => left.reference === right.reference

function matches(account: AccountReferenceRead, query: string) {
  const needle = query.trim().toLowerCase()
  return (
    needle === "" ||
    account.reference.toLowerCase().includes(needle) ||
    (account.name ?? "").toLowerCase().includes(needle)
  )
}

/** Search customer accounts by reference or name. A value that is not in
 * the list (a blank line, a typo, "remitx deposit") stays as typed, so a
 * demo statement can still include lines that will not match. */
export function AccountReferenceCombobox({
  id,
  accounts,
  value,
  onChange,
  disabled,
  placeholder = "Search accounts",
}: {
  id?: string
  accounts: AccountReferenceRead[]
  value: string
  onChange: (reference: string) => void
  disabled?: boolean
  placeholder?: string
}) {
  const selected =
    accounts.find((account) => account.reference === value) ?? null

  return (
    <Combobox
      items={accounts}
      value={selected}
      inputValue={value}
      onInputValueChange={(next, details) => {
        // The list closes by clearing a filter that matched nothing. That
        // typed reference is the value, so keep it.
        if (details.reason === "input-clear") return
        if (next !== value) onChange(next)
      }}
      onValueChange={(account) => {
        if (account) onChange(account.reference)
      }}
      itemToStringLabel={labelOf}
      itemToStringValue={labelOf}
      isItemEqualToValue={sameReference}
      filter={matches}
      autoHighlight
      disabled={disabled}
    >
      <ComboboxInput
        id={id}
        className="w-full"
        placeholder={placeholder}
        disabled={disabled}
        aria-label={id ? undefined : placeholder}
      />
      <ComboboxContent>
        <ComboboxEmpty>No account matches that.</ComboboxEmpty>
        <ComboboxList>
          {(account: AccountReferenceRead) => (
            <ComboboxItem key={account.reference} value={account}>
              <span className="font-mono">{account.reference}</span>
              {account.name ? (
                <span className="text-muted-foreground">
                  {account.name} · {account.currency}
                </span>
              ) : (
                <span className="text-muted-foreground">
                  {account.currency}
                </span>
              )}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
