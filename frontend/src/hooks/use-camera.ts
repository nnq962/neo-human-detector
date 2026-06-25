import { useQuery } from "@tanstack/react-query"
import { camerasApi } from "@/api/cameras.api"

export function useCamera(id: string) {
  return useQuery({
    queryKey: ["cameras", id],
    queryFn: () => camerasApi.get(id),
    enabled: !!id,
  })
}
