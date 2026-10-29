import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "~/lib/api"
import { applyToastOption } from "~/lib/mutation-toast"
import { createQueryClient } from "~/lib/query-client"

const toast = vi.hoisted(() => ({
  loading: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  dismiss: vi.fn(),
}))

vi.mock("sonner", () => ({ toast }))

describe("applyToastOption", () => {
  it("keeps the summary when a call does not set toast", () => {
    expect(
      applyToastOption({ meta: { summary: "Grant a role to a user" } })
    ).toEqual({ meta: { summary: "Grant a role to a user" } })
  })

  it("turns a string into the success line and false into an opt-out", () => {
    expect(
      applyToastOption({
        meta: { summary: "Grant a role to a user" },
        toast: "Role granted",
      })
    ).toEqual({
      meta: {
        summary: "Grant a role to a user",
        toast: { success: "Role granted" },
      },
    })
    expect(applyToastOption({ toast: false }).meta?.toast).toBe(false)
  })
})

describe("mutation toasts", () => {
  beforeEach(() => {
    toast.loading.mockClear()
    toast.success.mockClear()
    toast.error.mockClear()
    toast.dismiss.mockClear()
  })

  it("moves a mutation from loading to the OpenAPI summary", async () => {
    const client = createQueryClient()
    await client
      .getMutationCache()
      .build(client, {
        meta: { summary: "Grant a role to a user" },
        mutationFn: async () => "ok",
      })
      .execute(undefined)

    expect(toast.loading).toHaveBeenCalledWith("Working…", {
      id: expect.stringMatching(/^mutation-/),
    })
    const id = toast.loading.mock.calls[0][1].id
    expect(toast.success).toHaveBeenCalledWith("Grant a role to a user", {
      id,
    })
    expect(toast.error).not.toHaveBeenCalled()
  })

  it("uses the call's own success copy and description", async () => {
    const client = createQueryClient()
    await client
      .getMutationCache()
      .build(client, {
        meta: {
          summary: "Open a currency account",
          toast: {
            success: (account: unknown) =>
              `${(account as { currency: string }).currency} account opened`,
            description: "Ready to send.",
          },
        },
        mutationFn: async () => ({ currency: "ZAR" }),
      })
      .execute(undefined)

    const id = toast.loading.mock.calls[0][1].id
    expect(toast.success).toHaveBeenCalledWith("ZAR account opened", {
      id,
      description: "Ready to send.",
    })
  })

  it("replaces the loading toast with the error", async () => {
    const client = createQueryClient()
    const mutation = client.getMutationCache().build(client, {
      mutationFn: async () => {
        throw new ApiError("raw", 409, { code: "stokvel_paused" })
      },
    })

    await expect(mutation.execute(undefined)).rejects.toThrow("raw")

    const id = toast.loading.mock.calls[0][1].id
    expect(toast.error).toHaveBeenCalledWith(
      "Stokvels are temporarily paused.",
      {
        id,
      }
    )
    expect(toast.success).not.toHaveBeenCalled()
  })

  it("dismisses the loading toast when a call opts out of an error", async () => {
    const client = createQueryClient()
    const mutation = client.getMutationCache().build(client, {
      meta: { toast: { error: () => false } },
      mutationFn: async () => {
        throw new Error("shown inline")
      },
    })

    await expect(mutation.execute(undefined)).rejects.toThrow("shown inline")

    const id = toast.loading.mock.calls[0][1].id
    expect(toast.dismiss).toHaveBeenCalledWith(id)
    expect(toast.error).not.toHaveBeenCalled()
  })

  it("stays quiet when the call opts out", async () => {
    const client = createQueryClient()
    await client
      .getMutationCache()
      .build(client, {
        meta: { toast: false, summary: "Start a review" },
        mutationFn: async () => "ok",
      })
      .execute(undefined)

    expect(toast.loading).not.toHaveBeenCalled()
    expect(toast.success).not.toHaveBeenCalled()
  })

  it("drops the loading toast when the session has expired", async () => {
    const client = createQueryClient()
    const mutation = client.getMutationCache().build(client, {
      mutationFn: async () => {
        throw new ApiError("No valid session.", 401)
      },
    })

    await expect(mutation.execute(undefined)).rejects.toThrow(
      "No valid session."
    )

    const id = toast.loading.mock.calls[0][1].id
    expect(toast.dismiss).toHaveBeenCalledWith(id)
    expect(toast.error).not.toHaveBeenCalled()
  })
})
