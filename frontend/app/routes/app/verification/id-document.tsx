import { zodResolver } from "@hookform/resolvers/zod"
import { useMemo, useState } from "react"
import { Controller, useForm } from "react-hook-form"
import * as z from "zod"

import { CountryCombobox } from "~/components/kyc/country-combobox"
import { KycDocumentUpload } from "~/components/kyc/kyc-document-upload"
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
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { useKycReference } from "~/hooks/use-kyc-reference"
import {
  errorMessage,
  useOnboarding,
  useSaveStep,
} from "~/hooks/use-onboarding"
import type { KycReferenceRead as KycReference } from "~/client"
import {
  countryName,
  numberLabel,
  resolveScheme,
  schemesForCountry,
} from "~/lib/kyc-reference"

function tomorrowIso() {
  const now = new Date()
  const tomorrow = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() + 1
  )
  return [
    tomorrow.getFullYear(),
    String(tomorrow.getMonth() + 1).padStart(2, "0"),
    String(tomorrow.getDate()).padStart(2, "0"),
  ].join("-")
}

/** Format is checked by the API, per scheme. Here: that each answer exists,
 * and that a passport has an expiry that is still ahead. */
function schemaFor(reference: KycReference) {
  return z
    .object({
      issuing_country: z.string().min(1, "Choose the country that issued it."),
      id_type: z.string().min(1, "Choose the kind of identification."),
      id_number: z.string().trim().min(1, "Enter the number."),
      id_expiry_date: z.string(),
    })
    .superRefine((values, context) => {
      const scheme = resolveScheme(
        reference,
        values.issuing_country,
        values.id_type
      )
      if (!scheme?.requires_expiry) return
      if (!values.id_expiry_date) {
        context.addIssue({
          code: "custom",
          path: ["id_expiry_date"],
          message: "Enter the expiry date printed on the document.",
        })
      } else if (values.id_expiry_date < tomorrowIso()) {
        context.addIssue({
          code: "custom",
          path: ["id_expiry_date"],
          message: "This passport has expired. Use a passport that is valid.",
        })
      }
    })
}

type Values = z.infer<ReturnType<typeof schemaFor>>

export default function IdDocument() {
  const onboarding = useOnboarding()
  const application = onboarding.application
  const reference = useKycReference()
  const save = useSaveStep("id-document")
  const [fileError, setFileError] = useState<string | null>(null)
  const schema = useMemo(() => schemaFor(reference), [reference])

  const initialCountry =
    application?.issuing_country ?? application?.nationality ?? ""
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      issuing_country: initialCountry,
      id_type:
        application?.id_type ??
        (initialCountry
          ? (schemesForCountry(reference, initialCountry)[0]?.id_type ?? "")
          : ""),
      id_number: application?.id_number ?? "",
      id_expiry_date: application?.id_expiry_date ?? "",
    },
  })

  const issuingCountry = form.watch("issuing_country")
  const idType = form.watch("id_type")
  const available = issuingCountry
    ? schemesForCountry(reference, issuingCountry)
    : []
  const scheme = issuingCountry
    ? resolveScheme(reference, issuingCountry, idType)
    : undefined
  const passportOnly = available.length === 1
  const hasId = onboarding.stored_document_types.includes("id_document")

  function onSubmit(values: Values) {
    const requiresExpiry = scheme?.requires_expiry ?? false
    save.mutate(
      {
        issuing_country: values.issuing_country,
        id_type: values.id_type,
        id_number: values.id_number,
        id_expiry_date: requiresExpiry ? values.id_expiry_date : null,
      },
      {
        // The API's format messages belong beside the field they are about.
        onError: (error) => {
          const message = errorMessage(error)
          if (/expired/i.test(message)) {
            form.setError("id_expiry_date", { message })
          } else if (/national ID issued by/i.test(message)) {
            form.setError("id_type", { message })
          } else if (/format/i.test(message)) {
            form.setError("id_number", { message })
          }
        },
      }
    )
  }

  const fieldErrorShown =
    save.isError &&
    Boolean(
      form.formState.errors.id_number ||
      form.formState.errors.id_type ||
      form.formState.errors.id_expiry_date
    )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Identification</CardTitle>
        <CardDescription>
          {scheme
            ? "Enter the details exactly as they appear on your document."
            : "Choose the country that issued your ID or passport."}
        </CardDescription>
      </CardHeader>
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={form.handleSubmit(onSubmit)}
      >
        <CardContent>
          <FieldGroup>
            <Controller
              name="issuing_country"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="issuing_country">
                    Issuing country
                  </FieldLabel>
                  <CountryCombobox
                    id="issuing_country"
                    countries={reference.countries}
                    value={field.value}
                    onBlur={field.onBlur}
                    invalid={fieldState.invalid}
                    onChange={(code) => {
                      field.onChange(code)
                      const offered = schemesForCountry(reference, code)
                      if (
                        !offered.some(
                          (option) =>
                            option.id_type === form.getValues("id_type")
                        )
                      ) {
                        form.setValue("id_type", offered[0]?.id_type ?? "")
                      }
                    }}
                  />
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            <Controller
              name="id_type"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="id_type">Identification</FieldLabel>
                  <Select
                    items={available.map((option) => ({
                      value: option.id_type,
                      label: option.label,
                    }))}
                    value={field.value || null}
                    onValueChange={(next) => field.onChange(next ?? "")}
                    disabled={!issuingCountry}
                  >
                    <SelectTrigger
                      id="id_type"
                      className="w-full"
                      aria-invalid={fieldState.invalid}
                    >
                      <SelectValue placeholder="Choose the issuing country first" />
                    </SelectTrigger>
                    <SelectContent alignItemWithTrigger={false}>
                      <SelectGroup>
                        {available.map((option) => (
                          <SelectItem
                            key={option.scheme}
                            value={option.id_type}
                          >
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  {passportOnly ? (
                    <FieldDescription>
                      For {countryName(reference, issuingCountry)}, we accept a
                      passport.
                    </FieldDescription>
                  ) : null}
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            <Controller
              name="id_number"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="id_number">
                    {numberLabel(scheme)}
                  </FieldLabel>
                  <Input
                    {...field}
                    id="id_number"
                    inputMode={scheme?.input_mode ?? "text"}
                    autoComplete="off"
                    aria-invalid={fieldState.invalid}
                  />
                  {scheme ? (
                    <FieldDescription>{scheme.number_hint}</FieldDescription>
                  ) : null}
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </Field>
              )}
            />
            {scheme?.requires_expiry ? (
              <Controller
                name="id_expiry_date"
                control={form.control}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor="id_expiry_date">
                      Expiry date
                    </FieldLabel>
                    <DatePicker
                      id="id_expiry_date"
                      range="future"
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
            ) : null}
            <Field>
              <FieldLabel htmlFor="id_file">Document</FieldLabel>
              <KycDocumentUpload
                id="id_file"
                applicationId={application?.application_id}
                documentType="id_document"
                hint={
                  idType === "passport"
                    ? "Drop a PDF or photo of your passport's photo page"
                    : "Drop a PDF or photo of your ID"
                }
                onError={setFileError}
              />
              <FieldDescription>
                {hasId
                  ? "A document is already on file. Upload again only to replace it."
                  : (scheme?.document_hint ??
                    "PDF, JPEG, PNG or WebP, up to 10 MB. A person will look at this.")}
              </FieldDescription>
            </Field>
          </FieldGroup>
        </CardContent>
        <StepActions
          error={
            fileError ??
            (save.isError && !fieldErrorShown ? errorMessage(save.error) : null)
          }
          pending={save.isPending}
        />
      </form>
    </Card>
  )
}
