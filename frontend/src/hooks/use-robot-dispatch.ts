import { useQuery, useQueryClient } from "@tanstack/react-query"
import { robotDispatchApi } from "@/api/robot-dispatch.api"

export function useRobotDispatchConfig() {
  return useQuery({ queryKey: ["robot-dispatch"], queryFn: robotDispatchApi.get })
}

export function useInvalidateRobotDispatch() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["robot-dispatch"] })
}
