import { useUser } from "@clerk/react-router"
import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect } from "react"
import { Controller, useForm } from "react-hook-form"
import { isSupportedCountry } from "react-phone-number-input"
import * as z from "zod"

import { StepActions } from "~/components/kyc/step-actions"
import { PhoneInput } from "~/components/reui/phone-input"
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
import { Input } from "~/components/ui/input"
import {
  errorMessage,
  useOnboarding,
  useSaveStep,
} from "~/hooks/use-onboarding"

const schema = z.object({
  // Same rule as the API: E.164, a plus and 8 to 15 digits.
  mobile_number: z
    .string()
    .trim()
    .regex(
      /^\+[1-9]\d{7,14}$/,
      "Use international format: a plus, the country code, then the number."
    ),
  email: z.email("Enter a valid email address."),
})

export default function Contact() {
  const { application } = useOnboarding()
  const { user } = useUser()
  const save = useSaveStep("contact")
  const country = application?.residential_country
  const defaultCountry = country && isSupportedCountry(country) ? country : "ZA"
  const accountEmail = user?.primaryEmailAddress?.emailAddress ?? ""
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      mobile_number: application?.mobile_number ?? "",
      email: application?.email ?? accountEmail,
    },
  })

  useEffect(() => {
    if (application?.email || !accountEmail) return
    if (form.getValues("email")) return
    form.setValue("email", accountEmail, { shouldDirty: false })
  }, [accountEmail, application?.email, form])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Contact</CardTitle>
        <CardDescription>
          How a reviewer reaches you about this application.
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
              name="mobile_number"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="mobile_number">Mobile number</FieldLabel>
                  <PhoneInput
                    id="mobile_number"
                    name={field.name}
                    value={field.value}
                    onChange={(value) => field.onChange(value ?? "")}
                    onBlur={field.onBlur}
                    defaultCountry={defaultCountry}
                    autoComplete="tel"
                    aria-invalid={fieldState.invalid}
                  />
                  <FieldDescription>
                    Pick the country, then type the number.
                  </FieldDescription>
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            <Controller
              name="email"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="email">Contact email</FieldLabel>
                  <Input
                    {...field}
                    id="email"
                    type="email"
                    autoComplete="email"
                    aria-invalid={fieldState.invalid}
                  />
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
