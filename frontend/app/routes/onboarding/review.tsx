import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { format, parseISO } from "date-fns"
import { Controller, useForm } from "react-hook-form"
import { Link, useNavigate } from "react-router"
import * as z from "zod"

import { UnsupportedJurisdictionNotice } from "~/components/kyc/residence-select"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { Checkbox } from "~/components/ui/checkbox"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"
import { useKycReference } from "~/hooks/use-kyc-reference"
import { errorMessage, useOnboarding } from "~/hooks/use-onboarding"
import { api } from "~/client"
import { pathForStep } from "~/lib/kyc-onboarding"
import {
  countryName,
  isOperatingCountry,
  resolveScheme,
} from "~/lib/kyc-reference"

const SOURCE_OF_FUNDS: Record<string, string> = {
  salary: "Salary",
  business_income: "Business income",
  savings: "Savings",
  investment: "Investment",
  gift: "Gift",
  pension: "Pension",
  other: "Other",
}

const schema = z.object({
  consent: z
    .boolean()
    .refine((value) => value, "Confirm you consent before submitting."),
})

function Row({
  label,
  value,
  to,
}: {
  label: string
  value: string
  to: string
}) {
  return (
    <Item size="sm" role="listitem">
      <ItemContent>
        <ItemDescription>{label}</ItemDescription>
        <ItemTitle>{value}</ItemTitle>
      </ItemContent>
      <ItemActions>
        <Button
          variant="ghost"
          size="sm"
          nativeButton={false}
          render={<Link to={to} />}
        >
          Edit
        </Button>
      </ItemActions>
    </Item>
  )
}

function display(value: string | null | undefined) {
  return value ? value : "—"
}

function displayDate(value: string | null | undefined) {
  return value ? format(parseISO(value), "d MMMM yyyy") : "—"
}

export default function Review() {
  const onboarding = useOnboarding()
  const application = onboarding.application
  const reference = useKycReference()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { consent: false },
  })
  const consented = form.watch("consent")
  const submit = useMutation({
    ...api.kyc.onboarding.submitApplication(),
    onSuccess: (data) => {
      queryClient.setQueryData(
        api.kyc.onboarding.getApplication().queryKey,
        data
      )
      navigate(pathForStep("status"))
    },
  })

  if (!application) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Review</CardTitle>
          <CardDescription>
            There is no draft yet.{" "}
            <Link to={pathForStep("welcome")} className="underline">
              Start verification
            </Link>
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const submitted = submit.data?.application?.status === "submitted"
  const scheme =
    application.issuing_country && application.id_type
      ? resolveScheme(
          reference,
          application.issuing_country,
          application.id_type
        )
      : undefined
  const residenceUnsupported =
    Boolean(application.residential_country) &&
    !isOperatingCountry(reference, application.residential_country)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review and submit</CardTitle>
        <CardDescription>
          Check your details, then submit for review.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {residenceUnsupported ? (
          <UnsupportedJurisdictionNotice reference={reference} />
        ) : null}
        <ItemGroup>
          <Row
            label="Name"
            value={display(application.full_name)}
            to={pathForStep("identity")}
          />
          <Row
            label="Date of birth"
            value={displayDate(application.date_of_birth)}
            to={pathForStep("identity")}
          />
          <Row
            label="Nationality"
            value={countryName(reference, application.nationality)}
            to={pathForStep("identity")}
          />
          <Row
            label="Identification"
            value={
              scheme
                ? `${scheme.label} ${display(application.id_number)}, issued by ${countryName(reference, application.issuing_country)}`
                : "—"
            }
            to={pathForStep("id-document")}
          />
          {scheme?.requires_expiry ? (
            <Row
              label="Expires"
              value={displayDate(application.id_expiry_date)}
              to={pathForStep("id-document")}
            />
          ) : null}
          <Row
            label="Address"
            value={[
              application.residential_line1,
              application.residential_line2,
              application.residential_city,
              application.residential_postal_code,
              application.residential_country
                ? countryName(reference, application.residential_country)
                : null,
            ]
              .filter(Boolean)
              .join(", ")}
            to={pathForStep("address")}
          />
          <Row
            label="Mobile"
            value={display(application.mobile_number)}
            to={pathForStep("contact")}
          />
          <Row
            label="Email"
            value={display(application.email)}
            to={pathForStep("contact")}
          />
          <Row
            label="Source of funds"
            value={
              SOURCE_OF_FUNDS[application.source_of_funds ?? ""] ??
              display(application.source_of_funds)
            }
            to={pathForStep("financial")}
          />
          <Row
            label="PEP / DPIP / FPPO"
            value={
              application.is_domestic_prominent_influential_person ||
              application.is_foreign_prominent_public_official ||
              application.is_pep_family_or_close_associate
                ? "Declared"
                : "None declared"
            }
            to={pathForStep("declarations")}
          />
        </ItemGroup>
      </CardContent>
      <form
        noValidate
        onSubmit={form.handleSubmit((values) =>
          submit.mutate({
            body: {
              expected_version: application.version,
              consent: values.consent,
            },
          })
        )}
      >
        <CardFooter className="flex flex-col items-stretch gap-4">
          <Controller
            name="consent"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field
                orientation="horizontal"
                data-invalid={fieldState.invalid}
                className="items-start"
              >
                <Checkbox
                  id="popia"
                  checked={field.value}
                  onCheckedChange={(value) => field.onChange(value === true)}
                  aria-invalid={fieldState.invalid}
                />
                <div className="flex flex-col gap-1">
                  <FieldLabel
                    htmlFor="popia"
                    className="leading-snug font-normal"
                  >
                    I consent to RemitX processing this information for FICA due
                    diligence.
                  </FieldLabel>
                  {fieldState.invalid ? (
                    <FieldError errors={[fieldState.error]} />
                  ) : null}
                </div>
              </Field>
            )}
          />
          {submit.isError ? (
            <Alert variant="destructive" aria-live="polite">
              <AlertTitle>Could not submit</AlertTitle>
              <AlertDescription>{errorMessage(submit.error)}</AlertDescription>
            </Alert>
          ) : null}
          {submitted ? (
            <Button
              nativeButton={false}
              render={<Link to={pathForStep("status")} />}
            >
              See status
            </Button>
          ) : (
            <Button
              type="submit"
              disabled={submit.isPending || residenceUnsupported || !consented}
            >
              {submit.isPending ? "Submitting…" : "Submit for review"}
            </Button>
          )}
        </CardFooter>
      </form>
    </Card>
  )
}
