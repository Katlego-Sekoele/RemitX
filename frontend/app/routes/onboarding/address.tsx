import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { Controller, useForm } from "react-hook-form"
import * as z from "zod"

import { KycDocumentUpload } from "~/components/kyc/kyc-document-upload"
import {
  ResidenceSelect,
  residenceFormValue,
  UnsupportedJurisdictionNotice,
} from "~/components/kyc/residence-select"
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
import { Input } from "~/components/ui/input"
import { useKycReference } from "~/hooks/use-kyc-reference"
import {
  errorMessage,
  useOnboarding,
  useSaveStep,
} from "~/hooks/use-onboarding"
import { OUTSIDE_OPERATING_COUNTRIES } from "~/lib/kyc-reference"

const schema = z.object({
  residential_line1: z.string().trim().min(1, "Enter your street address."),
  residential_line2: z.string().trim(),
  residential_city: z.string().trim().min(1, "Enter your city or town."),
  residential_postal_code: z.string().trim().min(1, "Enter your postal code."),
  residential_country: z
    .string()
    .min(1, "Choose the country you live in.")
    .refine((value) => value !== OUTSIDE_OPERATING_COUNTRIES, {
      message: "We can only verify residents of the countries listed.",
    }),
})

type Values = z.infer<typeof schema>

const TEXT_FIELDS: {
  name: Exclude<keyof Values, "residential_country">
  label: string
  autoComplete: string
  description?: string
}[] = [
  {
    name: "residential_line1",
    label: "Address line 1",
    autoComplete: "address-line1",
  },
  {
    name: "residential_line2",
    label: "Suburb / unit",
    autoComplete: "address-line2",
    description: "Optional.",
  },
  { name: "residential_city", label: "City", autoComplete: "address-level2" },
  {
    name: "residential_postal_code",
    label: "Postal code",
    autoComplete: "postal-code",
  },
]

export default function Address() {
  const onboarding = useOnboarding()
  const application = onboarding.application
  const reference = useKycReference()
  const save = useSaveStep("address")
  const [fileError, setFileError] = useState<string | null>(null)
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      residential_line1: application?.residential_line1 ?? "",
      residential_line2: application?.residential_line2 ?? "",
      residential_city: application?.residential_city ?? "",
      residential_postal_code: application?.residential_postal_code ?? "",
      residential_country: residenceFormValue(
        reference,
        application?.residential_country
      ),
    },
  })
  const outside =
    form.watch("residential_country") === OUTSIDE_OPERATING_COUNTRIES
  const hasProof = onboarding.stored_document_types.includes("proof_of_address")

  return (
    <Card>
      <CardHeader>
        <CardTitle>Address</CardTitle>
        <CardDescription>Where you live now.</CardDescription>
      </CardHeader>
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={form.handleSubmit((values) =>
          save.mutate({
            ...values,
            residential_line2: values.residential_line2 || null,
          })
        )}
      >
        <CardContent>
          <FieldGroup>
            {TEXT_FIELDS.map((text) => (
              <Controller
                key={text.name}
                name={text.name}
                control={form.control}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor={text.name}>{text.label}</FieldLabel>
                    <Input
                      {...field}
                      id={text.name}
                      autoComplete={text.autoComplete}
                      aria-invalid={fieldState.invalid}
                    />
                    {text.description ? (
                      <FieldDescription>{text.description}</FieldDescription>
                    ) : null}
                    {fieldState.invalid ? (
                      <FieldError errors={[fieldState.error]} />
                    ) : null}
                  </Field>
                )}
              />
            ))}
            <Controller
              name="residential_country"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid && !outside}>
                  <FieldLabel htmlFor="residential_country">Country</FieldLabel>
                  <ResidenceSelect
                    id="residential_country"
                    reference={reference}
                    value={field.value}
                    onChange={field.onChange}
                    invalid={fieldState.invalid && !outside}
                  />
                  {fieldState.invalid && !outside ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            {outside ? (
              <UnsupportedJurisdictionNotice reference={reference} />
            ) : null}
            <Field>
              <FieldLabel htmlFor="proof">Proof of address</FieldLabel>
              <KycDocumentUpload
                id="proof"
                applicationId={application?.application_id}
                documentType="proof_of_address"
                hint="Drop a utility bill or bank statement"
                onError={setFileError}
              />
              <FieldDescription>
                {hasProof
                  ? "A document is already on file. Upload again only to replace it."
                  : "Utility bill or bank statement from the last 3 months. PDF, JPEG, PNG or WebP, up to 10 MB."}
              </FieldDescription>
            </Field>
          </FieldGroup>
        </CardContent>
        <StepActions
          error={fileError ?? (save.isError ? errorMessage(save.error) : null)}
          pending={save.isPending}
          disabled={outside}
        />
      </form>
    </Card>
  )
}
