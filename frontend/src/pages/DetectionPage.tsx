import { useState } from "react"
import { Check, Pencil, X } from "lucide-react"
import { toast } from "sonner"
import {
  detectionApi,
  type DetectionBatchSize,
  type DetectionConfig,
  type DetectionModelSize,
  type DetectionTask,
} from "@/api/detection.api"
import { useDetectionConfig, useInvalidateDetection } from "@/hooks/use-detection"
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

// ── Constants ─────────────────────────────────────────────────────────────────

const TASK_OPTIONS = [
  { value: "detect",  label: "Detect",  desc: "Phát hiện đối tượng (bounding box)" },
  { value: "pose",    label: "Pose",    desc: "Ước lượng tư thế (keypoints + bounding box)" },
]

const SIZE_OPTIONS = [
  { value: "nano",   label: "Nano (n)",   speedDots: 5, accDots: 1, note: "Nhanh nhất, nhẹ nhất" },
  { value: "small",  label: "Small (s)",  speedDots: 4, accDots: 2, note: "Phù hợp thiết bị edge" },
  { value: "medium", label: "Medium (m)", speedDots: 3, accDots: 3, note: "Cân bằng tốc độ & độ chính xác" },
  { value: "large",  label: "Large (l)",  speedDots: 2, accDots: 4, note: "Chính xác cao" },
  { value: "xlarge", label: "XLarge (x)", speedDots: 1, accDots: 5, note: "Chính xác nhất" },
]

// ── Shared helpers ────────────────────────────────────────────────────────────

function FieldLabel({ label, desc }: { label: string; desc?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium">{label}</span>
      {desc && <span className="text-[11px] leading-snug text-muted-foreground">{desc}</span>}
    </div>
  )
}

// ── Model size reference card ─────────────────────────────────────────────────

function DotBar({ filled, total = 5, color }: { filled: number; total?: number; color: string }) {
  return (
    <div className="flex gap-1">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className={`size-2 rounded-sm ${i < filled ? color : "bg-muted"}`} />
      ))}
    </div>
  )
}

function ModelSizeCard({ currentSize }: { currentSize: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Tham khảo model size</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-10 pl-4 pr-0" />
              <TableHead className="text-xs text-muted-foreground">Model</TableHead>
              <TableHead className="text-xs text-muted-foreground">Tốc độ</TableHead>
              <TableHead className="text-xs text-muted-foreground">Độ chính xác</TableHead>
              <TableHead className="hidden text-xs text-muted-foreground sm:table-cell">Ghi chú</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {SIZE_OPTIONS.map(({ value, label, speedDots, accDots, note }) => {
              const active = value === currentSize
              return (
                <TableRow key={value} className={active ? "bg-muted/50 hover:bg-muted/50" : ""}>
                  <TableCell className="w-10 pl-4 pr-0">
                    {active && <Check className="size-4 text-primary" />}
                  </TableCell>
                  <TableCell>
                    <span className={active ? "font-semibold" : "text-muted-foreground"}>{label}</span>
                  </TableCell>
                  <TableCell>
                    <DotBar filled={speedDots} color="bg-blue-400 dark:bg-blue-500" />
                  </TableCell>
                  <TableCell>
                    <DotBar filled={accDots} color="bg-green-400 dark:bg-green-500" />
                  </TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground sm:table-cell">{note}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

// ── Config card ───────────────────────────────────────────────────────────────

function DetectionConfigCard({
  config,
  onSaved,
}: {
  config: DetectionConfig
  onSaved: () => void
}) {
  const [draft, setDraft] = useState<DetectionConfig>({ ...config })
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  function startEdit() { setDraft({ ...config }); setEditing(true) }
  function cancel() { setEditing(false) }
  async function save() {
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

  const v = editing ? draft : config
  const taskLabel = TASK_OPTIONS.find((o) => o.value === v.task)?.label ?? v.task
  const sizeLabel = SIZE_OPTIONS.find((o) => o.value === v.model_size)?.label ?? v.model_size

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Cấu hình</CardTitle>
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
              <Button size="sm" onClick={save} disabled={saving}>
                <Check />
                {saving ? "Đang lưu..." : "Lưu"}
              </Button>
            </div>
          )}
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Task */}
          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Task" desc="Loại tác vụ YOLO" />
            {editing ? (
              <Select
                value={draft.task}
                onValueChange={(val) => setDraft((p) => ({ ...p, task: val as DetectionTask }))}
              >
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent position="popper" className="w-fit min-w-0">
                  {TASK_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex h-8 items-center">
                <Badge variant="outline">{taskLabel}</Badge>
              </div>
            )}
          </div>

          {/* Model size */}
          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Model size" desc="Kích thước mô hình YOLO" />
            {editing ? (
              <Select
                value={draft.model_size}
                onValueChange={(val) => setDraft((p) => ({ ...p, model_size: val as DetectionModelSize }))}
              >
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent position="popper" className="w-fit min-w-0">
                  {SIZE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex h-8 items-center">
                <Badge variant="outline">{sizeLabel}</Badge>
              </div>
            )}
          </div>

          {/* Batch size */}
          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Batch size" desc="Số frame xử lý song song" />
            {editing ? (
              <Select
                value={String(draft.batch_size)}
                onValueChange={(val) => setDraft((p) => ({ ...p, batch_size: parseInt(val) as DetectionBatchSize }))}
              >
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent position="popper" className="w-fit min-w-0">
                  {[1, 2, 4, 8].map((n) => (
                    <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex h-8 items-center text-sm">{v.batch_size}</div>
            )}
          </div>

          {/* Confidence */}
          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Confidence threshold" desc="Ngưỡng tin cậy tối thiểu để chấp nhận detection" />
            {editing ? (
              <div className="flex h-8 items-center gap-3">
                <Slider
                  min={0}
                  max={1}
                  step={0.01}
                  value={[draft.conf]}
                  onValueChange={([val]) => setDraft((p) => ({ ...p, conf: val }))}
                  className="flex-1"
                />
                <span className="w-9 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
                  {draft.conf.toFixed(2)}
                </span>
              </div>
            ) : (
              <div className="flex h-8 items-center text-sm">{v.conf}</div>
            )}
          </div>

          {/* Verbose */}
          <div className="sm:col-span-2 flex items-center justify-between gap-4 border-t pt-4">
            <FieldLabel label="Verbose" desc="In thêm thông tin debug ra console trong quá trình xử lý" />
            {editing
              ? <Switch checked={draft.verbose} onCheckedChange={(val) => setDraft((p) => ({ ...p, verbose: val }))} />
              : <Badge variant={v.verbose ? "default" : "secondary"}>{v.verbose ? "Bật" : "Tắt"}</Badge>
            }
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function DetectionPage() {
  const { data: config, isLoading, isError, refetch } = useDetectionConfig()
  const invalidateDetection = useInvalidateDetection()

  function handleSaved() {
    invalidateDetection()
    refetch()
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (isError || !config) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Detection</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Không tải được cấu hình Detection.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <DetectionConfigCard config={config} onSaved={handleSaved} />
      <ModelSizeCard currentSize={config.model_size} />
    </div>
  )
}
