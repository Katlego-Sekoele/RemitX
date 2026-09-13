import { zodResolver } from "@hookform/resolvers/zod"
import { format } from "date-fns"
import { Controller, useForm } from "react-hook-form"
import * as z from "zod"

import { CountryCombobox } from "~/components/kyc/country-combobox"
import { StepActions } from "~/components/kyc/step-actions"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { DatePicker } from "~/components/ui/date-picker"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { useKycReference } from "~/hooks/use-kyc-reference"
import {
  errorMessage,
  useOnboarding,
  useSaveStep,
} from "~/hooks/use-onboarding"

const schema = z.object({
  full_name: z
    .string()
    .trim()
    .min(2, "Enter your full legal name, as it appears on your ID."),
  date_of_birth: z.iso
    .date("Enter your date of birth.")
    // ISO dates compare correctly as strings.
    .refine(
      (value) => value <= format(new Date(), "yyyy-MM-dd"),
      "Date of birth can't be in the future."
    ),
  nationality: z.string().min(1, "Choose your nationality."),
})

export default function Identity() {
  const { application } = useOnboarding()
  const reference = useKycReference()
  const save = useSaveStep("identity")
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      full_name: application?.full_name ?? "",
      date_of_birth: application?.date_of_birth ?? "",
      nationality: application?.nationality ?? "",
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>About you</CardTitle>
        <CardDescription>
          Use your name as it appears on your ID.
        </CardDescription>
      </CardHeader>
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={form.handleSubmit((values) => save.mutate(values))}
      >
        <CardContent>
          <FieldGroup>
            <Controller
              name="full_name"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="full_name">Full legal name</FieldLabel>
                  <Input
                    {...field}
                    id="full_name"
                    autoComplete="name"
                    aria-invalid={fieldState.invalid}
                  />
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            <Controller
              name="date_of_birth"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="date_of_birth">Date of birth</FieldLabel>
                  <DatePicker
                    id="date_of_birth"
                    value={field.value}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                    invalid={fieldState.invalid}
                  />
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            <Controller
              name="nationality"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="nationality">Nationality</FieldLabel>
                  <CountryCombobox
                    id="nationality"
                    countries={reference.countries}
                    value={field.value}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                    invalid={fieldState.invalid}
                  />
                  <FieldDescription>
                    Your citizenship. It can differ from where you live.
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
