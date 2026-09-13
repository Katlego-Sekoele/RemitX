import { zodResolver } from "@hookform/resolvers/zod"
import { useMemo } from "react"
import { Controller, useForm } from "react-hook-form"
import * as z from "zod"

import { StepActions } from "~/components/kyc/step-actions"
import {
  Card,
  CardContent,
  CardDescription,
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
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "~/components/ui/input-group"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { Textarea } from "~/components/ui/textarea"
import {
  errorMessage,
  useOnboarding,
  useSaveStep,
} from "~/hooks/use-onboarding"

const FUNDS = [
  { value: "salary", label: "Salary" },
  { value: "business_income", label: "Business income" },
  { value: "savings", label: "Savings" },
  { value: "investment", label: "Investment" },
  { value: "gift", label: "Gift" },
  { value: "pension", label: "Pension" },
  { value: "other", label: "Other" },
] as const

function sanitizeZarAmount(value: string) {
  const cleaned = value.replace(/[^\d.]/g, "")
  const dot = cleaned.indexOf(".")
  if (dot === -1) return cleaned
  const whole = cleaned.slice(0, dot)
  const fraction = cleaned
    .slice(dot + 1)
    .replace(/\./g, "")
    .slice(0, 2)
  return `${whole}.${fraction}`
}

function schemaFor(declaresPep: boolean) {
  return z
    .object({
      source_of_funds: z.string().min(1, "Choose where this money comes from."),
      source_of_funds_detail: z.string().trim(),
      expected_monthly_volume_zar: z
        .string()
        .trim()
        .min(1, "Enter roughly how much you expect to send each month.")
        .regex(/^\d+(\.\d{1,2})?$/, "Enter an amount in rand, like 5000."),
      source_of_wealth: z.string().trim(),
    })
    .superRefine((values, context) => {
      if (
        values.source_of_funds === "other" &&
        !values.source_of_funds_detail
      ) {
        context.addIssue({
          code: "custom",
          path: ["source_of_funds_detail"],
          message: "Describe where the money comes from.",
        })
      }
      if (declaresPep && !values.source_of_wealth) {
        context.addIssue({
          code: "custom",
          path: ["source_of_wealth"],
          message:
            "Required because you declared a politically exposed person.",
        })
      }
    })
}

type Values = z.infer<ReturnType<typeof schemaFor>>

export default function Financial() {
  const { application } = useOnboarding()
  const save = useSaveStep("financial")
  const declaresPep = Boolean(
    application &&
    (application.is_domestic_prominent_influential_person ||
      application.is_foreign_prominent_public_official ||
      application.is_pep_family_or_close_associate)
  )
  const schema = useMemo(() => schemaFor(declaresPep), [declaresPep])
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      source_of_funds: application?.source_of_funds ?? "",
      source_of_funds_detail: application?.source_of_funds_detail ?? "",
      expected_monthly_volume_zar:
        application?.expected_monthly_volume_zar ?? "",
      source_of_wealth: application?.source_of_wealth ?? "",
    },
  })
  const source = form.watch("source_of_funds")

  return (
    <Card>
      <CardHeader>
        <CardTitle>Financial profile</CardTitle>
        <CardDescription>
          Where this money comes from, and roughly how much you expect to send
          each month.
        </CardDescription>
      </CardHeader>
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={form.handleSubmit((values) =>
          save.mutate({
            source_of_funds: values.source_of_funds,
            source_of_funds_detail:
              values.source_of_funds === "other"
                ? values.source_of_funds_detail
                : null,
            expected_monthly_volume_zar: values.expected_monthly_volume_zar,
            source_of_wealth: values.source_of_wealth || null,
          })
        )}
      >
        <CardContent>
          <FieldGroup>
            <Controller
              name="source_of_funds"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="source_of_funds">
                    Source of funds
                  </FieldLabel>
                  <Select
                    items={FUNDS}
                    value={field.value || null}
                    onValueChange={(next) => field.onChange(next ?? "")}
                  >
                    <SelectTrigger
                      id="source_of_funds"
                      className="w-full"
                      aria-invalid={fieldState.invalid}
                    >
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                    <SelectContent alignItemWithTrigger={false}>
                      <SelectGroup>
                        {FUNDS.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            {source === "other" ? (
              <Controller
                name="source_of_funds_detail"
                control={form.control}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor="source_of_funds_detail">
                      Please describe
                    </FieldLabel>
                    <Textarea
                      {...field}
                      id="source_of_funds_detail"
                      aria-invalid={fieldState.invalid}
                    />
                    {fieldState.invalid ? (
                      <FieldError errors={[fieldState.error]} />
                    ) : null}
                  </Field>
                )}
              />
            ) : null}
            <Controller
              name="expected_monthly_volume_zar"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="expected_monthly_volume_zar">
                    Expected monthly send (ZAR)
                  </FieldLabel>
                  <InputGroup>
                    <InputGroupAddon>
                      <InputGroupText>R</InputGroupText>
                    </InputGroupAddon>
                    <InputGroupInput
                      {...field}
                      id="expected_monthly_volume_zar"
                      type="text"
                      inputMode="decimal"
                      autoComplete="off"
                      spellCheck={false}
                      aria-invalid={fieldState.invalid}
                      onChange={(event) =>
                        field.onChange(sanitizeZarAmount(event.target.value))
                      }
                    />
                  </InputGroup>
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            <Controller
              name="source_of_wealth"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="source_of_wealth">
                    Source of wealth
                  </FieldLabel>
                  <Textarea
                    {...field}
                    id="source_of_wealth"
                    aria-invalid={fieldState.invalid}
                  />
                  <FieldDescription>
                    {declaresPep
                      ? "Required because of your politically exposed person declaration."
                      : "Optional unless you declare a politically exposed person on the next step."}
                  </FieldDescription>
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
          </FieldGroup>
        </CardContent>
        <StepActions
          error={save.isError ? errorMessage(save.error) : null}
          pending={save.isPending}
        />
      </form>
    </Card>
  )
}
