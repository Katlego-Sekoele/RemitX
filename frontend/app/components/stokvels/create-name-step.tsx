import { useState } from "react"

import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { currencyName } from "~/lib/money"
import { MAX_NAME_LENGTH, nameIssue } from "~/lib/stokvel-create"

export function CreateNameStep({
  name,
  goal,
  currency,
  currencies,
  onNameChange,
  onGoalChange,
  onCurrencyChange,
  onContinue,
}: {
  name: string
  goal: string
  currency: string
  /** The Stokvel currency options: fiat accounts the organiser holds. */
  currencies: readonly string[]
  onNameChange: (name: string) => void
  onGoalChange: (goal: string) => void
  onCurrencyChange: (currency: string) => void
  onContinue: () => void
}) {
  const [touched, setTouched] = useState(false)
  const issue = nameIssue(name)
  const showIssue = touched && issue !== null
  const items = currencies.map((value) => ({
    value,
    label: `${value} · ${currencyName(value)}`,
  }))

  return (
    <Card>
      <form
        noValidate
        className="flex flex-col gap-(--card-spacing)"
        onSubmit={(event) => {
          event.preventDefault()
          setTouched(true)
          if (issue === null) onContinue()
        }}
      >
        <CardHeader>
          <CardTitle>Name your stokvel</CardTitle>
          <CardDescription>
            Members see the name and goal on their invitation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <Field data-invalid={showIssue}>
              <FieldLabel htmlFor="stokvel-name">Name</FieldLabel>
              <Input
                id="stokvel-name"
                value={name}
                maxLength={MAX_NAME_LENGTH}
                placeholder="December groceries"
                autoFocus
                aria-invalid={showIssue}
                onChange={(event) => onNameChange(event.target.value)}
                onBlur={() => setTouched(true)}
              />
              {showIssue ? <FieldError>{issue}</FieldError> : null}
            </Field>
            <Field>
              <FieldLabel htmlFor="stokvel-goal">
                Goal <span className="text-muted-foreground">(optional)</span>
              </FieldLabel>
              <Input
                id="stokvel-goal"
                value={goal}
                maxLength={120}
                placeholder="Family support, school fees…"
                onChange={(event) => onGoalChange(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="stokvel-currency">Currency</FieldLabel>
              <Select
                items={items}
                value={currency}
                onValueChange={(next) => {
                  if (next) onCurrencyChange(next)
                }}
              >
                <SelectTrigger id="stokvel-currency" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {items.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldDescription>
                Every member pays from their account in this currency, so only
                people who hold one can be invited.
              </FieldDescription>
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="submit">Continue</Button>
        </CardFooter>
      </form>
    </Card>
  )
}
