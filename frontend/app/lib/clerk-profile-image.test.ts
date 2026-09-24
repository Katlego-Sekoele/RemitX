import { describe, expect, it } from "vitest"

import { clerkProfileImageUrl } from "~/lib/clerk-profile-image"

describe("clerkProfileImageUrl", () => {
  it("appends Clerk image optimization params", () => {
    expect(clerkProfileImageUrl("https://img.clerk.com/abc", 64)).toBe(
      "https://img.clerk.com/abc?width=64&height=64&fit=crop"
    )
  })

  it("uses & when the base URL already has query params", () => {
    expect(clerkProfileImageUrl("https://img.clerk.com/abc?foo=1", 32)).toBe(
      "https://img.clerk.com/abc?foo=1&width=32&height=32&fit=crop"
    )
  })
})
