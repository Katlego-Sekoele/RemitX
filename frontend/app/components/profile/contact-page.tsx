import { zodResolver } from "@hookform/resolvers/zod"
import { PlusIcon } from "@phosphor-icons/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { formatPhoneNumberIntl } from "react-phone-number-input"
import * as z from "zod"

import { api, type ProfileRead } from "~/client"
import { PhoneInput } from "~/components/reui/phone-input"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import {
  SettingsAction,
  SettingsEditCard,
  SettingsEditCardFooter,
  SettingsEditCardTitle,
  SettingsItem,
  SettingsPage,
  SettingsSection,
  SettingsSectionContent,
  SettingsSectionLabel,
  SettingsSwap,
  SettingsTitle,
} from "~/components/ui/settings"
import { errorMessage } from "~/hooks/use-onboarding"

const schema = z.object({
  // Same rule as the API: E.164.
  mobile_number: z
    .string()
    .trim()
    .regex(
      /^\+[1-9]\d{7,14}$/,
      "Use international format: a plus, the country code, then the number."
    ),
})

type Values = z.infer<typeof schema>

/** Clerk owns name, email and security; the contact mobile is ours. A custom
 * page inside Clerk's `<UserProfile>`, laid out like Clerk's own sections. */
export function ContactPage({ profile }: { profile: ProfileRead }) {
  const [editing, setEditing] = useState(false)
  const mobile = profile.mobile_number

  return (
    <SettingsPage>
      <SettingsTitle>Contact details</SettingsTitle>
      <SettingsSection>
        <SettingsSectionLabel>Mobile number</SettingsSectionLabel>
        <SettingsSectionContent>
          <SettingsSwap swapKey={editing ? "edit" : "view"}>
            {editing ? (
              <MobileForm mobile={mobile} onDone={() => setEditing(false)} />
            ) : mobile ? (
              <SettingsItem>
                {formatPhoneNumberIntl(mobile) || mobile}
                <SettingsAction
                  className="ml-auto"
                  onClick={() => setEditing(true)}
                >
                  Update mobile number
                </SettingsAction>
              </SettingsItem>
            ) : (
              <SettingsAction onClick={() => setEditing(true)}>
                <PlusIcon data-icon="inline-start" />
                Add mobile number
              </SettingsAction>
            )}
          </SettingsSwap>
        </SettingsSectionContent>
      </SettingsSection>
    </SettingsPage>
  )
}

function MobileForm({
  mobile,
  onDone,
}: {
  mobile: string | null
  onDone: () => void
}) {
  const queryClient = useQueryClient()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    // Not on blur: blurring the field to press Cancel would show an error that
    // moves Cancel out from under the pointer.
    mode: "onSubmit",
    defaultValues: { mobile_number: mobile ?? "" },
  })
  const update = useMutation({
    ...api.me.updateMyProfile(),
    onSuccess: (data) => {
      queryClient.setQueryData(api.me.getMyProfile().queryKey, data)
      onDone()
    },
  })

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit((values) =>
        update.mutate({ body: { mobile_number: values.mobile_number } })
      )}
    >
      <SettingsEditCard>
        <SettingsEditCardTitle>
          {mobile ? "Update mobile number" : "Add mobile number"}
        </SettingsEditCardTitle>
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
                defaultCountry="ZA"
                autoComplete="tel"
                autoFocus
                aria-invalid={fieldState.invalid}
              />
              {fieldState.invalid ? (
                <FieldError errors={[fieldState.error]} />
              ) : null}
            </Field>
          )}
        />
        {update.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage(update.error)}</AlertDescription>
          </Alert>
        ) : null}
        <SettingsEditCardFooter>
          {mobile ? (
            <Button
              type="button"
              variant="destructive"
              className="mr-auto"
              disabled={update.isPending}
              onClick={() => update.mutate({ body: { mobile_number: null } })}
            >
              Remove
            </Button>
          ) : null}
          <SettingsAction type="button" onClick={onDone}>
            Cancel
          </SettingsAction>
          <Button
            type="submit"
            disabled={!form.formState.isDirty || update.isPending}
          >
            Save
          </Button>
        </SettingsEditCardFooter>
      </SettingsEditCard>
    </form>
  )
}
