import type { Meta, StoryObj } from "@storybook/react-vite"

import type { BeneficiaryRead } from "~/client"

import { BeneficiaryList, BeneficiaryListSkeleton } from "./beneficiary-list"

// Shaped as the API sends them: contacts arrive masked, and someone who is
// not verified yet has only their first name and no country.
const beneficiaries: BeneficiaryRead[] = [
  {
    beneficiary_id: "00000000-0000-4000-8000-000000000001",
    linked_user_id: "00000000-0000-4000-8000-000000000101",
    profile_image_url: null,
    full_name: "Tendai Moyo",
    country: "ZW",
    country_name: "Zimbabwe",
    masked_email: "t•••@example.com",
    masked_mobile_number: "+2637••••••23",
    payout_currency: "ZWL",
    payout_currencies: ["ZAR", "ZWL"],
    relationship: "sibling",
    created_at: "2026-09-20T09:30:00Z",
  },
  {
    beneficiary_id: "00000000-0000-4000-8000-000000000002",
    linked_user_id: "00000000-0000-4000-8000-000000000102",
    profile_image_url: null,
    full_name: "Sian Naidoo",
    country: "ZA",
    country_name: "South Africa",
    masked_email: "s•••@example.com",
    masked_mobile_number: null,
    payout_currency: "ZAR",
    payout_currencies: ["ZAR"],
    relationship: "friend",
    created_at: "2026-09-18T14:05:00Z",
  },
  {
    beneficiary_id: "00000000-0000-4000-8000-000000000003",
    linked_user_id: "00000000-0000-4000-8000-000000000103",
    profile_image_url: null,
    full_name: "Naledi",
    country: null,
    country_name: null,
    masked_email: null,
    masked_mobile_number: "+2648••••••45",
    payout_currency: "NAD",
    payout_currencies: ["ZAR", "NAD"],
    relationship: "parent",
    created_at: "2026-09-12T08:00:00Z",
  },
]

const meta = {
  component: BeneficiaryList,
  args: { beneficiaries },
  parameters: { layout: "padded" },
  decorators: [
    (Story) => (
      <div className="max-w-2xl">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof BeneficiaryList>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

/** What the Beneficiaries page shows while the list loads. */
export const Loading: Story = {
  render: () => <BeneficiaryListSkeleton />,
}
