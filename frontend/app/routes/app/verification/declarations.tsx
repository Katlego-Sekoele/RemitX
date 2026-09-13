import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect, type ReactNode } from "react"
import { Controller, useForm, useWatch, type Control } from "react-hook-form"
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
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { RadioGroup, RadioGroupItem } from "~/components/ui/radio-group"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { Textarea } from "~/components/ui/textarea"
import { useKycReference } from "~/hooks/use-kyc-reference"
import {
  errorMessage,
  useOnboarding,
  useSaveStep,
} from "~/hooks/use-onboarding"
import type { KycCountryRead as KycCountry } from "~/client"

const answer = z.enum(["yes", "no"], "Answer yes or no.")

const schema = z
  .object({
    is_domestic_prominent_influential_person: answer,
    is_foreign_prominent_public_official: answer,
    is_pep_family_or_close_associate: answer,
    pep_relationship: z.string(),
    pep_position: z.string().trim(),
    pep_country: z.string(),
    pep_details: z.string().trim(),
  })
  .superRefine((values, context) => {
    if (!declaresPep(values)) return
    if (!isSelfPep(values) && !values.pep_relationship) {
      context.addIssue({
        code: "custom",
        path: ["pep_relationship"],
        message: "Choose how you relate to the prominent person.",
      })
    }
    if (!values.pep_position) {
      context.addIssue({
        code: "custom",
        path: ["pep_position"],
        message: "Enter the position held.",
      })
    }
    if (!values.pep_country) {
      context.addIssue({
        code: "custom",
        path: ["pep_country"],
        message: "Choose the country of that position.",
      })
    }
  })

type Values = z.input<typeof schema>

function declaresPep(values: Partial<Values>) {
  return (
    values.is_domestic_prominent_influential_person === "yes" ||
    values.is_foreign_prominent_public_official === "yes" ||
    values.is_pep_family_or_close_associate === "yes"
  )
}

function isSelfPep(values: Partial<Values>) {
  return (
    values.is_domestic_prominent_influential_person === "yes" ||
    values.is_foreign_prominent_public_official === "yes"
  )
}

function asAnswer(value: boolean | null | undefined) {
  if (value === true) return "yes"
  if (value === false) return "no"
  return undefined
}

type RelationshipOption = { value: string; label: string }

export default function Declarations() {
  const onboarding = useOnboarding()
  const application = onboarding.application
  const reference = useKycReference()
  const save = useSaveStep("declarations")
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      is_domestic_prominent_influential_person: asAnswer(
        application?.is_domestic_prominent_influential_person
      ),
      is_foreign_prominent_public_official: asAnswer(
        application?.is_foreign_prominent_public_official
      ),
      is_pep_family_or_close_associate: asAnswer(
        application?.is_pep_family_or_close_associate
      ),
      pep_relationship: application?.pep_relationship ?? "",
      pep_position: application?.pep_position ?? "",
      pep_country: application?.pep_country ?? "",
      pep_details: application?.pep_details ?? "",
    },
  })
  // Only the three answers decide whether the follow-ups show. Watching the
  // whole form here froze the page as the follow-up fields mounted.
  const [dpip, fppo, associate] = useWatch({
    control: form.control,
    name: [
      "is_domestic_prominent_influential_person",
      "is_foreign_prominent_public_official",
      "is_pep_family_or_close_associate",
    ],
  })
  const answers = {
    is_domestic_prominent_influential_person: dpip,
    is_foreign_prominent_public_official: fppo,
    is_pep_family_or_close_associate: associate,
  }
  const selfPep = isSelfPep(answers)
  const associateOnly = associate === "yes" && !selfPep
  const relationships = onboarding.pep_relationships.map((row) => ({
    value: row.relationship,
    label: row.description,
  }))
  const associateRelationships = relationships.filter(
    (row) => row.value !== "self"
  )

  useEffect(() => {
    const current = form.getValues("pep_relationship")
    if (selfPep) {
      if (current !== "self") {
        form.setValue("pep_relationship", "self", { shouldDirty: false })
      }
      return
    }
    if (current === "self") {
      form.setValue("pep_relationship", "", { shouldDirty: false })
    }
  }, [form, selfPep])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Declarations</CardTitle>
        <CardDescription>
          Tell us if you or someone close to you holds a prominent public
          position.
        </CardDescription>
      </CardHeader>
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={form.handleSubmit((values) => {
          const yes = declaresPep(values)
          const self = isSelfPep(values)
          save.mutate({
            is_domestic_prominent_influential_person:
              values.is_domestic_prominent_influential_person === "yes",
            is_foreign_prominent_public_official:
              values.is_foreign_prominent_public_official === "yes",
            is_pep_family_or_close_associate:
              values.is_pep_family_or_close_associate === "yes",
            pep_relationship: yes
              ? self
                ? "self"
                : values.pep_relationship
              : null,
            pep_position: yes ? values.pep_position : null,
            pep_country: yes ? values.pep_country : null,
            pep_details: yes ? values.pep_details || null : null,
          })
        })}
      >
        <CardContent>
          <FieldGroup>
            <DeclarationCard
              title="Are you a domestic prominent influential person?"
              description="For example, a senior South African government, judicial, military or party official."
            >
              <YesNo
                control={form.control}
                name="is_domestic_prominent_influential_person"
                question="Are you a domestic prominent influential person?"
              />
              {dpip === "yes" ? (
                <PepFollowUps
                  control={form.control}
                  countries={reference.countries}
                  subject="you"
                />
              ) : null}
            </DeclarationCard>
            <DeclarationCard
              title="Are you a foreign prominent public official?"
              description="The same kind of role, for another country."
            >
              <YesNo
                control={form.control}
                name="is_foreign_prominent_public_official"
                question="Are you a foreign prominent public official?"
              />
              {fppo === "yes" && dpip !== "yes" ? (
                <PepFollowUps
                  control={form.control}
                  countries={reference.countries}
                  subject="you"
                />
              ) : null}
            </DeclarationCard>
            <DeclarationCard
              title="Are you a family member or close associate of either?"
              description="FICA §21H."
            >
              <YesNo
                control={form.control}
                name="is_pep_family_or_close_associate"
                question="Are you a family member or close associate of either?"
              />
              {associateOnly ? (
                <PepFollowUps
                  control={form.control}
                  countries={reference.countries}
                  relationships={associateRelationships}
                  subject="they"
                />
              ) : null}
            </DeclarationCard>
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

function DeclarationCard({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <FieldGroup>{children}</FieldGroup>
      </CardContent>
    </Card>
  )
}

function YesNo({
  control,
  name,
  question,
}: {
  control: Control<Values>
  name:
    | "is_domestic_prominent_influential_person"
    | "is_foreign_prominent_public_official"
    | "is_pep_family_or_close_associate"
  question: string
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <FieldSet data-invalid={fieldState.invalid}>
          <FieldLegend className="sr-only">{question}</FieldLegend>
          <RadioGroup
            name={name}
            value={field.value ?? null}
            onValueChange={(value) => {
              field.onChange(value)
              field.onBlur()
            }}
            className="flex gap-6"
          >
            {(["no", "yes"] as const).map((option) => (
              <Field
                key={option}
                orientation="horizontal"
                data-invalid={fieldState.invalid}
                className="w-auto"
              >
                <RadioGroupItem
                  value={option}
                  id={`${name}-${option}`}
                  aria-invalid={fieldState.invalid}
                />
                <FieldLabel
                  htmlFor={`${name}-${option}`}
                  className="font-normal"
                >
                  {option === "yes" ? "Yes" : "No"}
                </FieldLabel>
              </Field>
            ))}
          </RadioGroup>
          {fieldState.invalid ? (
            <FieldError errors={[fieldState.error]} />
          ) : null}
        </FieldSet>
      )}
    />
  )
}

function PepFollowUps({
  control,
  countries,
  relationships,
  subject,
}: {
  control: Control<Values>
  countries: KycCountry[]
  relationships?: RelationshipOption[]
  subject: "you" | "they"
}) {
  const positionLabel = subject === "you" ? "Your position" : "Their position"
  const positionDescription =
    subject === "you"
      ? "The office you hold or held."
      : "The office they hold or held."

  return (
    <>
      {relationships ? (
        <Controller
          name="pep_relationship"
          control={control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="pep_relationship">Relationship</FieldLabel>
              <Select
                items={relationships}
                value={field.value || null}
                onValueChange={(next) => field.onChange(next ?? "")}
              >
                <SelectTrigger
                  id="pep_relationship"
                  className="w-full"
                  aria-invalid={fieldState.invalid}
                >
                  <SelectValue placeholder="Select" />
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  <SelectGroup>
                    {relationships.map((row) => (
                      <SelectItem key={row.value} value={row.value}>
                        {row.label}
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
      ) : null}
      <Controller
        name="pep_position"
        control={control}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="pep_position">{positionLabel}</FieldLabel>
            <Input
              {...field}
              id="pep_position"
              aria-invalid={fieldState.invalid}
            />
            <FieldDescription>{positionDescription}</FieldDescription>
            {fieldState.invalid ? (
              <FieldError errors={[fieldState.error]} />
            ) : null}
          </Field>
        )}
      />
      <Controller
        name="pep_country"
        control={control}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="pep_country">Country</FieldLabel>
            <CountryCombobox
              id="pep_country"
              countries={countries}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              invalid={fieldState.invalid}
            />
            <FieldDescription>
              Where the position is or was held.
            </FieldDescription>
            {fieldState.invalid ? (
              <FieldError errors={[fieldState.error]} />
            ) : null}
          </Field>
        )}
      />
      <Controller
        name="pep_details"
        control={control}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="pep_details">Details</FieldLabel>
            <Textarea {...field} id="pep_details" />
            <FieldDescription>Optional.</FieldDescription>
          </Field>
        )}
      />
    </>
  )
}
