import { useQuery, useQueryClient } from "@tanstack/react-query"
import { uartApi } from "@/api/uart.api"

export function useUartConfig() {
  return useQuery({ queryKey: ["uart"], queryFn: uartApi.get })
}

export function useUartStatus() {
  return useQuery({
    queryKey: ["uart", "status"],
    queryFn: uartApi.getStatus,
    refetchInterval: 2000,
  })
}

export function useInvalidateUart() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["uart"] })
}
