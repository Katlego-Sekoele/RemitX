import type { Meta, StoryObj } from "@storybook/react-vite"
import { fn } from "storybook/test"

import type { BeneficiaryLookupResponse } from "~/client"

import { AddBeneficiaryForm, ConfirmStep } from "./add-beneficiary-form"

// What the lookup answers for "tendai1-zwl": a short name and country, never
// an email or mobile.
const found: BeneficiaryLookupResponse = {
  linked_user_id: "00000000-0000-4000-8000-000000000101",
  profile_image_url: null,
  first_name: "Tendai",
  display_name: "Tendai M.",
  country: "ZW",
  country_name: "Zimbabwe",
  account_currency: "ZWL",
  payout_currencies: ["ZAR", "ZWL"],
}

const onBack = fn()

const meta = {
  component: AddBeneficiaryForm,
  args: { onCancel: fn(), onAdded: fn() },
  parameters: { layout: "padded" },
  decorators: [
    (Story) => (
      <div className="max-w-2xl">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof AddBeneficiaryForm>

export default meta
type Story = StoryObj<typeof meta>

/**
 * The first step: the account reference the recipient shared. **Find** looks
 * it up on the API; Confirm shows where that leads.
 */
export const Default: Story = {}

/**
 * The second step, once the lookup has found who the reference belongs to.
 * The payout currency starts as the reference's own.
 */
export const Confirm: Story = {
  render: ({ onCancel, onAdded }) => (
    <ConfirmStep
      found={found}
      onBack={onBack}
      onCancel={onCancel}
      onAdded={onAdded}
    />
  ),
}
