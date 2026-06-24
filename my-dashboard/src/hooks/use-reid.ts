import { useQuery, useQueryClient } from "@tanstack/react-query"
import { reidApi } from "@/api/reid.api"

export function useReidConfig() {
  return useQuery({ queryKey: ["reid"], queryFn: reidApi.get })
}

export function useInvalidateReid() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["reid"] })
}
