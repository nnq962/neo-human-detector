import { useQuery, useQueryClient } from "@tanstack/react-query"
import { camerasApi } from "@/api/cameras.api"

export { type Camera } from "@/api/cameras.api"

export function useCameras() {
  return useQuery({
    queryKey: ["cameras"],
    queryFn: camerasApi.list,
  })
}

export function useInvalidateCameras() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["cameras"] })
}
