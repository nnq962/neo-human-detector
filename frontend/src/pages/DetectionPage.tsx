import { useState } from "react"
import { Check, ChevronDown, Pencil, RefreshCw, X } from "lucide-react"
import { toast } from "sonner"
import {
  detectionApi,
  type DetectionConfig,
} from "@/api/detection.api"
import type { ModelArtifact } from "@/api/models.api"
import { useDetectionConfig, useInvalidateDetection } from "@/hooks/use-detection"
import { useModels } from "@/hooks/use-models"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Slider } from "@/components/ui/slider"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"

function FieldLabel({ label, desc }: { label: string; desc?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium">{label}</span>
      {desc && <span className="text-[11px] leading-snug text-muted-foreground">{desc}</span>}
    </div>
  )
}

function titleCase(value: string | null) {
  if (!value) return "—"
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function backendLabel(backend: string) {
  const labels: Record<string, string> = {
    onnx: "ONNX",
    pytorch: "PyTorch",
    rknn: "RKNN",
    tensorrt: "TensorRT",
  }
  return labels[backend.toLocaleLowerCase()] ?? titleCase(backend)
}

function modelFamily(model: ModelArtifact) {
  const pathParts = model.path.replace(/^weights\//, "").split("/")
  const backendIndex = pathParts.findIndex(
    (part) => part.toLocaleLowerCase() === model.backend.toLocaleLowerCase(),
  )
  return pathParts[backendIndex + 1] ?? model.task ?? "Khác"
}

function ModelPicker({
  models,
  value,
  onValueChange,
}: {
  models: ModelArtifact[]
  value: string | null
  onValueChange: (modelId: string) => void
}) {
  const backends = [...new Set(models.map((model) => model.backend))].sort()
  const selectedModel = models.find((model) => model.id === value)
  const selectedLabel = selectedModel
    ? `${backendLabel(selectedModel.backend)} / ${modelFamily(selectedModel).toUpperCase()} / ${selectedModel.version.toUpperCase()} / ${titleCase(selectedModel.task)} · ${titleCase(selectedModel.variant)}`
    : "Chọn detection model"

  return (
    <div className="space-y-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="font-normal">
            <span>{selectedLabel}</span>
            <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="max-h-80" align="start">
        {backends.map((backend) => {
          const backendModels = models.filter((model) => model.backend === backend)
          return (
            <DropdownMenuSub key={backend}>
              <DropdownMenuSubTrigger>{backendLabel(backend)}</DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="max-h-80 min-w-52 overflow-y-auto">
              {[...new Set(backendModels.map(modelFamily))].sort().map((family) => {
                const familyModels = backendModels.filter((model) => modelFamily(model) === family)
                return (
                  <DropdownMenuSub key={family}>
                    <DropdownMenuSubTrigger>{family.toUpperCase()}</DropdownMenuSubTrigger>
                    <DropdownMenuSubContent className="max-h-80 min-w-52 overflow-y-auto">
                    {[...new Set(familyModels.map((model) => model.version))].sort().map((version) => {
                      const versionModels = familyModels.filter((model) => model.version === version)
                      return (
                        <DropdownMenuSub key={version}>
                          <DropdownMenuSubTrigger>{version.toUpperCase()}</DropdownMenuSubTrigger>
                          <DropdownMenuSubContent className="max-h-80 min-w-64 overflow-y-auto">
                          {[...new Set(versionModels.map((model) => model.task ?? "Khác"))].sort().map((task) => {
                            const taskModels = versionModels.filter((model) => (model.task ?? "Khác") === task)
                            return (
                              <DropdownMenuSub key={task}>
                                <DropdownMenuSubTrigger>{titleCase(task)}</DropdownMenuSubTrigger>
                                <DropdownMenuSubContent className="max-h-80 min-w-56 overflow-y-auto">
                                {taskModels.map((model) => {
                                  const selected = model.id === value
                                  return (
                                    <DropdownMenuItem
                                      key={model.id}
                                      onSelect={() => onValueChange(model.id)}
                                      className={selected ? "bg-primary/10 text-primary" : undefined}
                                    >
                                      <span className="min-w-0 flex-1 truncate">{titleCase(model.variant)}</span>
                                      {selected && <Check className="size-4 shrink-0" aria-label="Đang được chọn" />}
                                    </DropdownMenuItem>
                                  )
                                })}
                                </DropdownMenuSubContent>
                              </DropdownMenuSub>
                            )
                          })}
                          </DropdownMenuSubContent>
                        </DropdownMenuSub>
                      )
                    })}
                    </DropdownMenuSubContent>
                  </DropdownMenuSub>
                )
              })}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          )
        })}
        </DropdownMenuContent>
      </DropdownMenu>
      <p className="text-[11px] text-muted-foreground">
        Chọn backend, họ model, phiên bản, task rồi chọn biến thể model.
      </p>
    </div>
  )
}

function DetectionConfigCard({
  config,
  models,
  onSaved,
}: {
  config: DetectionConfig
  models: ModelArtifact[]
  onSaved: () => void
}) {
  const [draft, setDraft] = useState<DetectionConfig>({ ...config })
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  function startEdit() {
    setDraft({ ...config })
    setEditing(true)
  }

  function cancel() {
    setEditing(false)
  }

  async function save() {
    if (!draft.model_id) {
      toast.error("Hãy chọn một detection model")
      return
    }

    setSaving(true)
    try {
      const response = await detectionApi.update(draft)
      toast.success(response.message)
      onSaved()
      setEditing(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Lưu cấu hình thất bại")
    } finally {
      setSaving(false)
    }
  }

  const value = editing ? draft : config
  const selectedModel = models.find((model) => model.id === value.model_id)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Cấu hình Detection</CardTitle>
          {!editing ? (
            <Button variant="blue" size="sm" onClick={startEdit}>
              <Pencil />
              Sửa
            </Button>
          ) : (
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={cancel} disabled={saving}>
                <X />
                Hủy
              </Button>
              <Button size="sm" onClick={save} disabled={saving || !draft.model_id}>
                <Check />
                {saving ? "Đang lưu..." : "Lưu"}
              </Button>
            </div>
          )}
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]">
          <div className="flex min-w-0 flex-col gap-1.5">
            <FieldLabel
              label="Model"
              desc="Danh sách được quét trực tiếp từ thư mục weights"
            />
            {editing ? (
              <ModelPicker
                models={models}
                value={draft.model_id}
                onValueChange={(modelId) => setDraft((current) => ({
                  ...current,
                  model_id: modelId,
                }))}
              />
            ) : (
              <div className="flex min-h-8 items-center gap-2">
                {selectedModel ? (
                  <>
                    <Badge variant="outline">{selectedModel.version.toUpperCase()}</Badge>
                    <Badge variant="outline">{titleCase(selectedModel.task)}</Badge>
                    <Badge variant="outline">{titleCase(selectedModel.variant)}</Badge>
                  </>
                ) : (
                  <Badge variant="destructive">Model không tồn tại</Badge>
                )}
              </div>
            )}
            <span className="truncate text-[11px] text-muted-foreground">
              {value.model_id ?? "Chưa chọn model"}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel
              label="Confidence threshold"
              desc="Ngưỡng tin cậy tối thiểu để chấp nhận detection"
            />
            {editing ? (
              <div className="flex h-8 items-center gap-3">
                <Slider
                  min={0}
                  max={1}
                  step={0.01}
                  value={[draft.conf]}
                  onValueChange={([confidence]) => setDraft((current) => ({
                    ...current,
                    conf: confidence,
                  }))}
                  className="flex-1"
                />
                <span className="w-9 text-right text-sm tabular-nums text-muted-foreground">
                  {draft.conf.toFixed(2)}
                </span>
              </div>
            ) : (
              <div className="flex h-8 items-center text-sm">{value.conf}</div>
            )}
          </div>

          <div className="flex items-center justify-between gap-4 border-t pt-4 lg:col-span-2">
            <FieldLabel label="Verbose" desc="In thêm thông tin debug khi inference" />
            {editing ? (
              <Switch
                checked={draft.verbose}
                onCheckedChange={(verbose) => setDraft((current) => ({
                  ...current,
                  verbose,
                }))}
              />
            ) : (
              <Badge variant={value.verbose ? "default" : "secondary"}>
                {value.verbose ? "Bật" : "Tắt"}
              </Badge>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function ModelCatalogCard({
  models,
  refreshing,
  onRefresh,
}: {
  models: ModelArtifact[]
  refreshing: boolean
  onRefresh: () => void
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Detection models khả dụng</CardTitle>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
            <RefreshCw className={refreshing ? "animate-spin" : ""} />
            Quét lại
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Version</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>Variant</TableHead>
              <TableHead>Backend</TableHead>
              <TableHead className="hidden lg:table-cell">Đường dẫn</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Không tìm thấy detection model trong weights.
                </TableCell>
              </TableRow>
            ) : models.map((model) => (
              <TableRow key={model.id}>
                <TableCell className="font-medium">{model.version.toUpperCase()}</TableCell>
                <TableCell>{titleCase(model.task)}</TableCell>
                <TableCell>{titleCase(model.variant)}</TableCell>
                <TableCell>{titleCase(model.backend)}</TableCell>
                <TableCell className="hidden max-w-96 truncate text-xs text-muted-foreground lg:table-cell">
                  {model.path}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function DetectionPage() {
  const configQuery = useDetectionConfig()
  const modelsQuery = useModels("detection")
  const invalidateDetection = useInvalidateDetection()

  function handleSaved() {
    invalidateDetection()
    configQuery.refetch()
  }

  if (configQuery.isLoading || modelsQuery.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (configQuery.isError || !configQuery.data || modelsQuery.isError) {
    return (
      <Card>
        <CardHeader><CardTitle>Detection</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Không tải được cấu hình hoặc model catalog.
          </p>
        </CardContent>
      </Card>
    )
  }

  const models = modelsQuery.data ?? []
  return (
    <div className="flex flex-col gap-4">
      <DetectionConfigCard
        config={configQuery.data}
        models={models}
        onSaved={handleSaved}
      />
      <ModelCatalogCard
        models={models}
        refreshing={modelsQuery.isFetching}
        onRefresh={() => modelsQuery.refetch()}
      />
    </div>
  )
}
