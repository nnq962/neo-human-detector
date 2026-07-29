import { useQuery } from "@tanstack/react-query"
import { modelsApi, type ModelKind } from "@/api/models.api"

export function useModels(kind?: ModelKind) {
  return useQuery({
    queryKey: ["models", kind ?? "all"],
    queryFn: () => modelsApi.get(kind),
  })
}
