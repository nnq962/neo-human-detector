import { useQuery, useQueryClient } from "@tanstack/react-query"
import { camerasApi } from "@/api/cameras.api"
import { runtimeConfigQueryKey } from "@/hooks/use-runtime-config"

export { type Camera } from "@/api/cameras.api"

export function useCameras() {
  return useQuery({
    queryKey: ["cameras"],
    queryFn: camerasApi.list,
  })
}

export function useInvalidateCameras() {
  const queryClient = useQueryClient()
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["cameras"] }),
    queryClient.invalidateQueries({ queryKey: runtimeConfigQueryKey }),
  ])
}
