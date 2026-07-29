import { apiRequest, type ApiResponse, unwrapApiResponse } from "./client"

export type ModelKind = "detection" | "reid"

export interface ModelArtifact {
  id: string
  kind: ModelKind
  backend: string
  version: string
  task: string | null
  variant: string | null
  format: string
  platforms: string[]
  batch_size: number | "dynamic" | null
  runtime_supported: boolean
  path: string
}

export const modelsApi = {
  get: (kind?: ModelKind) => {
    const query = kind ? `?kind=${kind}` : ""
    return apiRequest<ApiResponse<ModelArtifact[]>>(`/models${query}`)
      .then(unwrapApiResponse)
  },
}
