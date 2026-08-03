import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { runtimeApi, type RuntimeConfigUpdate } from "@/api/runtime.api"

export const runtimeConfigQueryKey = ["runtime-config"] as const

export function useRuntimeConfig() {
  return useQuery({
    queryKey: runtimeConfigQueryKey,
    queryFn: runtimeApi.getConfig,
  })
}

export function useUpdateRuntimeConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (update: RuntimeConfigUpdate) => runtimeApi.updateConfig(update),
    onSuccess: (config) => {
      queryClient.setQueryData(runtimeConfigQueryKey, config)
    },
  })
}
