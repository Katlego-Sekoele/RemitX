import { toast } from "sonner"

import { ApiError } from "~/lib/api"
import { stokvelErrorMessage } from "~/lib/stokvel-errors"

const DEFAULT_LOADING = "Working…"
const DEFAULT_SUCCESS = "Done"

/**
 * Copy for the toast every mutation raises, unless `toast` is `false`.
 * A string is used as-is. A function sees the mutation result; `false`
 * drops the toast (the loading one is dismissed).
 */
export type MutationToastConfig = {
  loading?: string
  success?: string | ((data: unknown, variables: unknown) => string | false)
  description?:
    string | ((data: unknown, variables: unknown) => string | undefined)
  error?: string | ((error: unknown, variables: unknown) => string | false)
}

export type MutationToastMeta = {
  /** HTTP method, stamped onto generated mutations. */
  method?: string
  /** OpenAPI summary. The success toast when the call does not override it. */
  summary?: string
  /** `false` leaves this call quiet. An object replaces the default copy. */
  toast?: false | MutationToastConfig
}

declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: MutationToastMeta
  }
}

type ToastMutation = {
  mutationId: number
  meta?: MutationToastMeta
}

function toastId(mutationId: number) {
  return `mutation-${mutationId}`
}

function configOf(
  meta: MutationToastMeta | undefined
): MutationToastConfig | false {
  if (meta?.toast === false) return false
  if (meta?.toast && typeof meta.toast === "object") return meta.toast
  return {}
}

function resolve(
  value: MutationToastConfig["success"] | MutationToastConfig["description"],
  fallback: string | undefined,
  data: unknown,
  variables: unknown
): string | false | undefined {
  if (typeof value === "function") {
    const resolved = value(data, variables)
    return resolved === undefined ? fallback : resolved
  }
  if (typeof value === "string") return value
  return fallback
}

function defaultSuccess(meta: MutationToastMeta | undefined) {
  return meta?.summary?.trim() || DEFAULT_SUCCESS
}

function defaultError(error: unknown) {
  return stokvelErrorMessage(error)
}

/** A signed-out session is sent to sign-in. A toast would flash on the way. */
function isSessionExpired(error: unknown) {
  return error instanceof ApiError && error.status === 401
}

export function showMutationLoading(mutation: ToastMutation) {
  const config = configOf(mutation.meta)
  if (config === false) return
  toast.loading(config.loading ?? DEFAULT_LOADING, {
    id: toastId(mutation.mutationId),
  })
}

export function showMutationSuccess(
  data: unknown,
  variables: unknown,
  mutation: ToastMutation
) {
  const config = configOf(mutation.meta)
  if (config === false) return
  const id = toastId(mutation.mutationId)
  const message = resolve(
    config.success,
    defaultSuccess(mutation.meta),
    data,
    variables
  )
  if (message === false) {
    toast.dismiss(id)
    return
  }
  const description = resolve(config.description, undefined, data, variables)
  toast.success(message, {
    id,
    ...(typeof description === "string" && description ? { description } : {}),
  })
}

export function showMutationError(
  error: unknown,
  variables: unknown,
  mutation: ToastMutation
) {
  const config = configOf(mutation.meta)
  if (config === false) return
  const id = toastId(mutation.mutationId)
  if (isSessionExpired(error)) {
    toast.dismiss(id)
    return
  }
  const message = resolve(config.error, defaultError(error), error, variables)
  if (message === false) {
    toast.dismiss(id)
    return
  }
  toast.error(message, { id })
}

/** What `useMutation({ toast })` accepts. A string is the success line. */
export type MutationToastOption = false | string | MutationToastConfig

/** Fold `toast` into `meta` and drop it, so React Query never sees the field. */
export function applyToastOption<
  T extends { meta?: MutationToastMeta; toast?: MutationToastOption },
>(options: T): Omit<T, "toast"> {
  const { toast: toastOption, ...rest } = options
  if (toastOption === undefined) return rest
  const toast =
    typeof toastOption === "string" ? { success: toastOption } : toastOption
  return {
    ...rest,
    meta: { ...rest.meta, toast },
  }
}
