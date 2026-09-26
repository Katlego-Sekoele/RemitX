import { describe, expect, it } from "vitest"

import { SettlementRecoveryKind } from "~/client"
import { canRetryEnqueue } from "~/lib/settlement-recovery"

describe("canRetryEnqueue", () => {
  it("allows retry only for fully pending groups", () => {
    expect(canRetryEnqueue(SettlementRecoveryKind.RETRY_ENQUEUE)).toBe(true)
    expect(canRetryEnqueue(SettlementRecoveryKind.MANUAL_ONLY)).toBe(false)
    expect(canRetryEnqueue(SettlementRecoveryKind.NONE)).toBe(false)
  })
})
