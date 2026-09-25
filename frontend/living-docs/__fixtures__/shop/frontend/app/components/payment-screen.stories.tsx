import type { Meta, StoryObj } from "@storybook/react-vite"

import { PaymentScreen } from "~/components/payment-screen"

const meta = {
  title: "Checkout/Payment screen",
  component: PaymentScreen,
} satisfies Meta<typeof PaymentScreen>

export default meta

export const Card: StoryObj<typeof meta> = {}

export const Declined: StoryObj<typeof meta> = {}
