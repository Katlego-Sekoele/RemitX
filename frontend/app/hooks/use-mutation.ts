import {
  useMutation as useQueryMutation,
  type DefaultError,
  type QueryClient,
  type UseMutationOptions,
  type UseMutationResult,
} from "@tanstack/react-query"

import {
  applyToastOption,
  type MutationToastConfig,
} from "~/lib/mutation-toast"

/**
 * `useMutation`, plus a toast for the round trip.
 *
 * Leave `toast` off and the success line is the OpenAPI summary.
 * A string replaces that line. `false` stays quiet. An object sets the
 * loading line, the description, or a success/error function (`false`
 * from a function drops that toast).
 */
export function useMutation<
  TData = unknown,
  TError = DefaultError,
  TVariables = void,
  TOnMutateResult = unknown,
>(
  options: UseMutationOptions<TData, TError, TVariables, TOnMutateResult> & {
    toast?:
      | false
      | string
      | {
          loading?: string
          success?:
            string | ((data: TData, variables: TVariables) => string | false)
          description?:
            | string
            | ((data: TData, variables: TVariables) => string | undefined)
          error?:
            string | ((error: TError, variables: TVariables) => string | false)
        }
  },
  queryClient?: QueryClient
): UseMutationResult<TData, TError, TVariables, TOnMutateResult> {
  return useQueryMutation(
    applyToastOption({
      ...options,
      toast: options.toast as MutationToastConfig | false | string | undefined,
    }),
    queryClient
  )
}
