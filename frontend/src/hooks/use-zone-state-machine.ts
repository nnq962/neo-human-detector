import { useQuery, useQueryClient } from "@tanstack/react-query"
import { zoneStateMachineApi } from "@/api/zone-state-machine.api"

export function useZoneStateMachineConfig() {
  return useQuery({
    queryKey: ["zone-state-machine"],
    queryFn: zoneStateMachineApi.get,
  })
}

export function useInvalidateZoneStateMachine() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["zone-state-machine"] })
}
