import { useState } from "react"
import { Check, Pencil, RefreshCw, X } from "lucide-react"
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"

const BATCH_OPTIONS = [1, 2, 4, 8]

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

function modelLabel(model: ModelArtifact) {
  return [
    model.version.toUpperCase(),
    titleCase(model.task),
    titleCase(model.variant),
    titleCase(model.backend),
  ].filter((part) => part !== "—").join(" · ")
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2 flex flex-col gap-1.5">
            <FieldLabel
              label="Model"
              desc="Danh sách được quét trực tiếp từ thư mục weights"
            />
            {editing ? (
              <Select
                value={draft.model_id ?? undefined}
                onValueChange={(modelId) => setDraft((current) => ({
                  ...current,
                  model_id: modelId,
                }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Chọn detection model" />
                </SelectTrigger>
                <SelectContent position="popper">
                  {models.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      {modelLabel(model)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
            <FieldLabel label="Batch size" desc="Số camera/frame xử lý song song" />
            {editing ? (
              <Select
                value={String(draft.batch_size)}
                onValueChange={(batchSize) => setDraft((current) => ({
                  ...current,
                  batch_size: Number(batchSize),
                }))}
              >
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent position="popper">
                  {BATCH_OPTIONS.map((batchSize) => (
                    <SelectItem key={batchSize} value={String(batchSize)}>
                      {batchSize}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex h-8 items-center text-sm">{value.batch_size}</div>
            )}
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

          <div className="sm:col-span-2 flex items-center justify-between gap-4 border-t pt-4">
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
      <div className="flex flex-col gap-6">
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
    <div className="flex flex-col gap-6">
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
