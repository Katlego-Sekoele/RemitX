import type { Meta, StoryObj } from "@storybook/react-vite"

import { ShippingForm } from "./shipping-form"

const meta = { component: ShippingForm } satisfies Meta<typeof ShippingForm>

export default meta

export const Empty: StoryObj<typeof meta> = {}
