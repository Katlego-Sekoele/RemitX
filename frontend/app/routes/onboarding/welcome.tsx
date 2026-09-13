import { zodResolver } from "@hookform/resolvers/zod"
import { IdentificationCardIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Controller, useForm } from "react-hook-form"
import { useNavigate } from "react-router"
import * as z from "zod"

import {
  ResidenceSelect,
  residenceFormValue,
  UnsupportedJurisdictionNotice,
} from "~/components/kyc/residence-select"
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
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "~/components/ui/field"
import { useKycReference } from "~/hooks/use-kyc-reference"
import { errorMessage, useOnboarding } from "~/hooks/use-onboarding"
import { pathForStep } from "~/lib/kyc-onboarding"
import { OUTSIDE_OPERATING_COUNTRIES } from "~/lib/kyc-reference"
import { api } from "~/client"

const schema = z.object({
  residence: z
    .string()
    .min(1, "Tell us where you live.")
    .refine((value) => value !== OUTSIDE_OPERATING_COUNTRIES, {
      message: "We can only verify residents of the countries listed.",
    }),
})

export default function Welcome() {
  const onboarding = useOnboarding()
  const reference = useKycReference()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      residence: residenceFormValue(
        reference,
        onboarding.application?.residential_country
      ),
    },
  })
  const start = useMutation({
    ...api.kyc.onboarding.startApplication(),
    onSuccess: (data) => {
      queryClient.setQueryData(
        api.kyc.onboarding.getApplication().queryKey,
        data
      )
      navigate(
        pathForStep(data.next_step === "welcome" ? "identity" : data.next_step)
      )
    },
  })
  const outside = form.watch("residence") === OUTSIDE_OPERATING_COUNTRIES

  return (
    <Card>
      <CardHeader>
        <CardTitle>Verification</CardTitle>
        <CardDescription>Takes about five minutes.</CardDescription>
      </CardHeader>
      <form
        className="flex flex-col gap-4"
        onSubmit={form.handleSubmit((values) =>
          start.mutate({ body: { residential_country: values.residence } })
        )}
      >
        <CardContent className="flex flex-col gap-5">
          <Controller
            name="residence"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid && !outside}>
                <FieldLabel htmlFor="residence">Where do you live?</FieldLabel>
                <ResidenceSelect
                  id="residence"
                  reference={reference}
                  value={field.value}
                  onChange={field.onChange}
                  invalid={fieldState.invalid && !outside}
                />
                <FieldDescription>
                  Where you live, not your nationality.
                </FieldDescription>
                {fieldState.invalid && !outside ? (
                  <FieldError errors={[fieldState.error]} />
                ) : null}
              </Field>
            )}
          />
          {outside ? (
            <UnsupportedJurisdictionNotice reference={reference} />
          ) : null}
          <div className="flex flex-col gap-2">
            <p>Have these to hand:</p>
            <ul className="list-disc space-y-1 pl-4">
              <li>Your national ID number, or your passport</li>
              <li>A photo of that document</li>
              <li>
                Proof of address (a recent utility bill or bank statement)
              </li>
              <li>Your mobile number and the name as it appears on the ID</li>
            </ul>
          </div>
          <p>You can leave and come back — your progress is saved.</p>
          {onboarding.standing.status === "approved" ? (
            <p>
              A reviewer has already approved an application on this account.
            </p>
          ) : null}
        </CardContent>
        <CardFooter className="flex flex-col items-stretch gap-3">
          {start.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Could not start</AlertTitle>
              <AlertDescription>{errorMessage(start.error)}</AlertDescription>
            </Alert>
          ) : null}
          <Button type="submit" disabled={start.isPending || outside}>
            <IdentificationCardIcon />
            {start.isPending ? "Starting…" : "Continue"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
