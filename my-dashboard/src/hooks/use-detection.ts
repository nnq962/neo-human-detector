import { useQuery, useQueryClient } from "@tanstack/react-query"
import { detectionApi } from "@/api/detection.api"

export function useDetectionConfig() {
  return useQuery({
    queryKey: ["detection"],
    queryFn: detectionApi.get,
  })
}

export function useInvalidateDetection() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["detection"] })
}
