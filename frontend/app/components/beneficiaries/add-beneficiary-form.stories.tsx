import type { Meta, StoryObj } from "@storybook/react-vite"
import { fn } from "storybook/test"

import { AddBeneficiaryForm } from "./add-beneficiary-form"

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
 * it up on the API, which a story has no session for, so the confirm step
 * that follows is not shown here.
 */
export const Default: Story = {}
