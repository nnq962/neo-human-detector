import { useEffect, useRef, useState } from "react"
import { Check, Pencil, X } from "lucide-react"
import { toast } from "sonner"
import {
  reidApi,
  type ReIdConfig,
  type ReIdDevice,
  type ReIdGalleryConfig,
  type ReIdQualityConfig,
  type ReIdTrackConfig,
} from "@/api/reid.api"
import { useInvalidateReid, useReidConfig } from "@/hooks/use-reid"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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

// ── Constants ─────────────────────────────────────────────────────────────────

const DEVICE_OPTIONS = [
  { value: "auto", label: "Auto" },
  { value: "cpu",  label: "CPU" },
  { value: "cuda", label: "CUDA (GPU)" },
  { value: "mps",  label: "MPS" },
]

type GeneralConfig = Pick<
  ReIdConfig,
  "enabled" | "zone_only" | "require_occupied_zone" | "model_path" | "device"
> & {
  embedding_batch_size: number
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function EditActions({
  editing, saving, onEdit, onCancel, onSave,
}: {
  editing: boolean; saving: boolean
  onEdit: () => void; onCancel: () => void; onSave: () => void
}) {
  if (!editing) {
    return (
      <Button variant="outline" size="sm" onClick={onEdit}>
        <Pencil />
        Sửa
      </Button>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={onCancel} disabled={saving}>
        <X />
        Hủy
      </Button>
      <Button size="sm" onClick={onSave} disabled={saving}>
        <Check />
        {saving ? "Đang lưu..." : "Lưu"}
      </Button>
    </div>
  )
}

function FieldLabel({ label, desc }: { label: string; desc?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium">{label}</span>
      {desc && <span className="text-[11px] leading-snug text-muted-foreground">{desc}</span>}
    </div>
  )
}

function BoolRow({
  label, desc, value, editing, onChange,
}: {
  label: string; desc: string; value: boolean
  editing: boolean; onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <FieldLabel label={label} desc={desc} />
      {editing
        ? <Switch checked={value} onCheckedChange={onChange} />
        : <Badge variant={value ? "default" : "secondary"}>{value ? "Bật" : "Tắt"}</Badge>
      }
    </div>
  )
}

function NumField({
  value, onChange, step = 1, min, max,
}: {
  value: number; onChange: (v: number) => void
  step?: number; min?: number; max?: number
}) {
  const [raw, setRaw] = useState(String(value))
  const synced = useRef(value)

  useEffect(() => {
    if (synced.current !== value) {
      synced.current = value
      setRaw(String(value))
    }
  }, [value])

  return (
    <Input
      type="number"
      step={step}
      min={min}
      max={max}
      value={raw}
      onChange={(e) => {
        setRaw(e.target.value)
        const n = parseFloat(e.target.value)
        if (!isNaN(n)) { synced.current = n; onChange(n) }
      }}
      onBlur={() => {
        const n = parseFloat(raw)
        if (isNaN(n) || raw.trim() === "") {
          setRaw(String(value)); synced.current = value
        } else {
          setRaw(String(n)); synced.current = n
        }
      }}
      onWheel={(e) => e.currentTarget.blur()}
      className="h-8 text-sm [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
    />
  )
}

function SliderField({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex h-8 items-center gap-3">
      <Slider
        min={0}
        max={1}
        step={0.01}
        value={[value]}
        onValueChange={([val]) => onChange(val)}
        className="flex-1"
      />
      <span className="w-9 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
        {value.toFixed(2)}
      </span>
    </div>
  )
}

// ── General card ──────────────────────────────────────────────────────────────

function GeneralCard({ config, onSaved }: { config: ReIdConfig; onSaved: () => void }) {
  const saved: GeneralConfig = {
    enabled: config.enabled,
    zone_only: config.zone_only,
    require_occupied_zone: config.require_occupied_zone,
    model_path: config.model_path,
    device: config.device,
    embedding_batch_size: config.embedding.batch_size,
  }
  const [draft, setDraft] = useState<GeneralConfig>({ ...saved })
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  function startEdit() { setDraft({ ...saved }); setEditing(true) }
  function cancel() { setEditing(false) }
  async function save() {
    setSaving(true)
    try {
      const response = await reidApi.update({
        enabled: draft.enabled,
        zone_only: draft.zone_only,
        require_occupied_zone: draft.require_occupied_zone,
        model_path: draft.model_path?.trim() || undefined,
        device: draft.device,
        embedding: { batch_size: draft.embedding_batch_size },
      })
      toast.success(response.message)
      onSaved()
      setEditing(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Lưu cấu hình thất bại")
    } finally {
      setSaving(false)
    }
  }

  const v = editing ? draft : saved

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Cấu hình chung</CardTitle>
          <EditActions editing={editing} saving={saving} onEdit={startEdit} onCancel={cancel} onSave={save} />
        </div>
      </CardHeader>

      <CardContent className="flex flex-col">
        <div className="flex flex-col divide-y">
          {/* Bool rows */}
          <div className="flex flex-col divide-y">
            <BoolRow
              label="Bật Re-ID"
              desc="Kích hoạt toàn bộ chức năng Re-ID"
              value={v.enabled}
              editing={editing}
              onChange={(val) => setDraft((p) => ({ ...p, enabled: val }))}
            />
            <BoolRow
              label="Chỉ trong zone"
              desc="Chỉ xử lý Re-ID cho người đang ở trong vùng (zone)"
              value={v.zone_only}
              editing={editing}
              onChange={(val) => setDraft((p) => ({ ...p, zone_only: val }))}
            />
            <BoolRow
              label="Yêu cầu zone có người"
              desc="Bỏ qua nếu zone chưa có người nào được xác nhận vào"
              value={v.require_occupied_zone}
              editing={editing}
              onChange={(val) => setDraft((p) => ({ ...p, require_occupied_zone: val }))}
            />
          </div>

          {/* Model / Device / Batch */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 pt-4 pb-1">
            <div className="sm:col-span-2 flex flex-col gap-1.5">
              <FieldLabel
                label="Model path"
                desc="Đường dẫn đến file trọng số mô hình Re-ID"
              />
              {editing ? (
                <Input
                  className="h-8 text-sm"
                  value={draft.model_path ?? ""}
                  onChange={(e) => setDraft((p) => ({ ...p, model_path: e.target.value }))}
                />
              ) : (
                <div className="flex h-8 items-center">
                  <span className="text-sm text-muted-foreground truncate">{saved.model_path ?? "—"}</span>
                </div>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <FieldLabel label="Device" desc="Thiết bị tính toán" />
              {editing ? (
                <Select
                  value={draft.device}
                  onValueChange={(val) => setDraft((p) => ({ ...p, device: val as ReIdDevice }))}
                >
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper" className="w-fit min-w-0">
                    {DEVICE_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <div className="flex h-8 items-center">
                  <Badge variant="outline">
                    {DEVICE_OPTIONS.find((o) => o.value === saved.device)?.label ?? saved.device}
                  </Badge>
                </div>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <FieldLabel
                label="Embedding batch size"
                desc="Số ảnh xử lý song song khi trích xuất embedding"
              />
              {editing ? (
                <NumField
                  value={draft.embedding_batch_size}
                  onChange={(val) => setDraft((p) => ({ ...p, embedding_batch_size: val }))}
                  min={1}
                />
              ) : (
                <div className="flex h-8 items-center text-sm">{saved.embedding_batch_size}</div>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Track card ───────────────────────────────────────────────────────────────

function TrackCard({ config, onSaved }: { config: ReIdTrackConfig; onSaved: () => void }) {
  const [draft, setDraft] = useState<ReIdTrackConfig>({ ...config })
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  function startEdit() { setDraft({ ...config }); setEditing(true) }
  function cancel() { setEditing(false) }
  async function save() {
    setSaving(true)
    try {
      const response = await reidApi.update({ track: draft })
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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Track & Buffer</CardTitle>
          <EditActions editing={editing} saving={saving} onEdit={startEdit} onCancel={cancel} onSave={save} />
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Buffer min (frames)" desc="Số frame tối thiểu để track được coi là ổn định" />
            {editing
              ? <NumField value={draft.buffer_min} onChange={(val) => setDraft((p) => ({ ...p, buffer_min: val }))} min={0} />
              : <div className="flex h-8 items-center text-sm">{v.buffer_min}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Grace period (frames)" desc="Số frame giữ lại track sau khi mất dấu" />
            {editing
              ? <NumField value={draft.grace_period} onChange={(val) => setDraft((p) => ({ ...p, grace_period: val }))} min={0} />
              : <div className="flex h-8 items-center text-sm">{v.grace_period}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Update interval (frames)" desc="Khoảng cách frame giữa hai lần cập nhật embedding" />
            {editing
              ? <NumField value={draft.update_interval} onChange={(val) => setDraft((p) => ({ ...p, update_interval: val }))} min={1} />
              : <div className="flex h-8 items-center text-sm">{v.update_interval}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Max buffer size" desc="Kích thước tối đa của embedding buffer mỗi track" />
            {editing
              ? <NumField value={draft.max_buffer_size} onChange={(val) => setDraft((p) => ({ ...p, max_buffer_size: val }))} min={1} />
              : <div className="flex h-8 items-center text-sm">{v.max_buffer_size}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Gallery cleanup interval (s)" desc="Chu kỳ (giây) dọn dẹp các entry cũ trong gallery" />
            {editing
              ? <NumField value={draft.gallery_cleanup_interval} onChange={(val) => setDraft((p) => ({ ...p, gallery_cleanup_interval: val }))} min={1} />
              : <div className="flex h-8 items-center text-sm">{v.gallery_cleanup_interval}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Max reverify misses" desc="Số lần thất bại tái xác minh trước khi xóa track" />
            {editing
              ? <NumField value={draft.max_reverify_misses} onChange={(val) => setDraft((p) => ({ ...p, max_reverify_misses: val }))} min={0} />
              : <div className="flex h-8 items-center text-sm">{v.max_reverify_misses}</div>
            }
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Quality card ──────────────────────────────────────────────────────────────

function QualityCard({ config, onSaved }: { config: ReIdQualityConfig; onSaved: () => void }) {
  const [draft, setDraft] = useState<ReIdQualityConfig>({ ...config })
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  function startEdit() { setDraft({ ...config }); setEditing(true) }
  function cancel() { setEditing(false) }
  async function save() {
    setSaving(true)
    try {
      const response = await reidApi.update({ quality: draft })
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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Lọc chất lượng mẫu</CardTitle>
          <EditActions editing={editing} saving={saving} onEdit={startEdit} onCancel={cancel} onSave={save} />
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Overlap IoU threshold" desc="Ngưỡng IoU để lọc bounding box bị che khuất" />
            {editing
              ? <SliderField value={draft.overlap_iou_threshold} onChange={(val) => setDraft((p) => ({ ...p, overlap_iou_threshold: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.overlap_iou_threshold}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Overlap IoA threshold" desc="Ngưỡng IoA để lọc bounding box bị che khuất" />
            {editing
              ? <SliderField value={draft.overlap_ioa_threshold} onChange={(val) => setDraft((p) => ({ ...p, overlap_ioa_threshold: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.overlap_ioa_threshold}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Stable bbox window (frames)" desc="Số frame để kiểm tra độ ổn định bounding box" />
            {editing
              ? <NumField value={draft.stable_bbox_window} onChange={(val) => setDraft((p) => ({ ...p, stable_bbox_window: val }))} min={1} />
              : <div className="flex h-8 items-center text-sm">{v.stable_bbox_window}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Stable center shift ratio" desc="Tỉ lệ dịch chuyển tâm tối đa để bbox được coi là ổn định" />
            {editing
              ? <SliderField value={draft.stable_center_shift_ratio} onChange={(val) => setDraft((p) => ({ ...p, stable_center_shift_ratio: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.stable_center_shift_ratio}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Stable size change ratio" desc="Tỉ lệ thay đổi kích thước tối đa để bbox được coi là ổn định" />
            {editing
              ? <SliderField value={draft.stable_size_change_ratio} onChange={(val) => setDraft((p) => ({ ...p, stable_size_change_ratio: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.stable_size_change_ratio}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Laplacian variance threshold" desc="Ngưỡng phương sai Laplacian để lọc ảnh bị mờ" />
            {editing
              ? <NumField value={draft.laplacian_var_threshold} onChange={(val) => setDraft((p) => ({ ...p, laplacian_var_threshold: val }))} step={0.1} min={0} />
              : <div className="flex h-8 items-center text-sm">{v.laplacian_var_threshold}</div>
            }
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Gallery card ──────────────────────────────────────────────────────────────

function GalleryCard({ config, onSaved }: { config: ReIdGalleryConfig; onSaved: () => void }) {
  const [draft, setDraft] = useState<ReIdGalleryConfig>({ ...config })
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  function startEdit() { setDraft({ ...config }); setEditing(true) }
  function cancel() { setEditing(false) }
  async function save() {
    setSaving(true)
    try {
      const response = await reidApi.update({ gallery: draft })
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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Gallery & Matching</CardTitle>
          <EditActions editing={editing} saving={saving} onEdit={startEdit} onCancel={cancel} onSave={save} />
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Sim threshold match" desc="Ngưỡng độ tương đồng để xác nhận khớp (match)" />
            {editing
              ? <SliderField value={draft.sim_threshold_match} onChange={(val) => setDraft((p) => ({ ...p, sim_threshold_match: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.sim_threshold_match}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="EMA alpha" desc="Hệ số làm mượt EMA khi cập nhật embedding vào gallery" />
            {editing
              ? <SliderField value={draft.ema_alpha} onChange={(val) => setDraft((p) => ({ ...p, ema_alpha: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.ema_alpha}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Max samples" desc="Số embedding mẫu tối đa trong gallery mỗi người" />
            {editing
              ? <NumField value={draft.max_samples} onChange={(val) => setDraft((p) => ({ ...p, max_samples: val }))} min={1} />
              : <div className="flex h-8 items-center text-sm">{v.max_samples}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="TTL (minutes)" desc="Thời gian sống (phút) của mỗi entry trong gallery" />
            {editing
              ? <NumField value={draft.ttl_minutes} onChange={(val) => setDraft((p) => ({ ...p, ttl_minutes: val }))} step={0.1} min={0.1} />
              : <div className="flex h-8 items-center text-sm">{v.ttl_minutes}</div>
            }
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ReidPage() {
  const { data: config, isLoading, isError, refetch } = useReidConfig()
  const invalidateReid = useInvalidateReid()

  function handleSaved() {
    invalidateReid()
    refetch()
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-72" />
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
        <Skeleton className="h-48" />
      </div>
    )
  }

  if (isError || !config) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Re-ID</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Không tải được cấu hình Re-ID.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <GeneralCard config={config} onSaved={handleSaved} />
      <TrackCard config={config.track} onSaved={handleSaved} />
      <QualityCard config={config.quality} onSaved={handleSaved} />
      <GalleryCard config={config.gallery} onSaved={handleSaved} />
    </div>
  )
}
