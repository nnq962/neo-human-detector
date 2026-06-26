import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { autoStartApi, type AutoStartConfigUpdate } from "@/api/auto-start.api"


export function useAutoStartConfig() {
  return useQuery({
    queryKey: ["auto-start"],
    queryFn: autoStartApi.get,
  })
}


export function useUpdateAutoStartConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: AutoStartConfigUpdate) => autoStartApi.update(data),
    onSuccess: (data) => {
      queryClient.setQueryData(["auto-start"], data)
    },
  })
}
