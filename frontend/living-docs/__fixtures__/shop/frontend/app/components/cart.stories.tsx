import type { Meta, StoryObj } from "@storybook/react-vite"

import { Cart } from "./cart"

const meta = { component: Cart } satisfies Meta<typeof Cart>

export default meta

export const Default: StoryObj<typeof meta> = {}
