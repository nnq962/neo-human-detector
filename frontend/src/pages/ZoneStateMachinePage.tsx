import { useEffect, useRef, useState } from "react"
import { Check, Pencil, X } from "lucide-react"
import { toast } from "sonner"
import {
  zoneStateMachineApi,
  type ZoneStateMachineConfig,
} from "@/api/zone-state-machine.api"
import {
  useInvalidateZoneStateMachine,
  useZoneStateMachineConfig,
} from "@/hooks/use-zone-state-machine"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"

// ── Helpers ───────────────────────────────────────────────────────────────────

function FieldLabel({ label, desc }: { label: string; desc?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium">{label}</span>
      {desc && <span className="text-[11px] leading-snug text-muted-foreground">{desc}</span>}
    </div>
  )
}

function NumField({
  value, onChange, step = 0.1, min = 0,
}: {
  value: number; onChange: (v: number) => void; step?: number; min?: number
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

// ── State diagram ─────────────────────────────────────────────────────────────

function StateBox({ label, sub, color }: {
  label: string; sub: string; color: "neutral" | "pending" | "occupied"
}) {
  const boxCls = {
    neutral:  "bg-muted/60 border-border",
    pending:  "bg-amber-500/10 border-amber-400/60 dark:border-amber-600/50",
    occupied: "bg-green-500/10 border-green-400/60 dark:border-green-600/50",
  }[color]
  const labelCls = {
    neutral:  "text-foreground",
    pending:  "text-amber-700 dark:text-amber-400",
    occupied: "text-green-700 dark:text-green-400",
  }[color]
  return (
    <div className={`w-full rounded-lg border-2 px-3 py-3 text-center ${boxCls}`}>
      <p className={`text-sm font-semibold ${labelCls}`}>{label}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>
    </div>
  )
}

function HArrow({ dir, label }: { dir: "left" | "right"; label: string }) {
  const head = dir === "right"
    ? <div className="h-0 w-0 shrink-0 border-y-[5px] border-y-transparent border-l-[7px] border-l-border" />
    : <div className="h-0 w-0 shrink-0 border-y-[5px] border-y-transparent border-r-[7px] border-r-border" />
  return (
    <div className="flex w-full flex-col items-center gap-1.5">
      {dir === "right" && <span className="text-[11px] text-muted-foreground">{label}</span>}
      <div className="flex w-full items-center">
        {dir === "left" && head}
        <div className="h-px flex-1 bg-border" />
        {dir === "right" && head}
      </div>
      {dir === "left" && <span className="text-[11px] text-muted-foreground">{label}</span>}
    </div>
  )
}

function VArrow({ dir, label, sublabel }: { dir: "up" | "down"; label: string; sublabel?: string }) {
  // up arrowhead: border-b visible → ▲
  // down arrowhead: border-t visible → ▼
  const head = dir === "up"
    ? <div className="h-0 w-0 shrink-0 border-x-[5px] border-x-transparent border-b-[7px] border-b-border" />
    : <div className="h-0 w-0 shrink-0 border-x-[5px] border-x-transparent border-t-[7px] border-t-border" />
  return (
    <div className="flex h-full w-full flex-col items-center gap-1 py-1">
      {dir === "up" && head}
      <div className="w-px flex-1 bg-border" />
      {dir === "down" && head}
      <span className="text-[11px] font-medium text-muted-foreground text-center">{label}</span>
      {sublabel && <span className="text-[10px] text-muted-foreground/60 text-center">{sublabel}</span>}
    </div>
  )
}

function StateDiagram({ config }: { config: ZoneStateMachineConfig }) {
  const { confirm_enter_time, confirm_exit_time, pending_enter_miss_grace_time } = config
  return (
    <div
      className="mx-auto grid w-full max-w-md select-none items-center gap-2"
      style={{ gridTemplateColumns: "1fr 56px 1fr", gridTemplateRows: "auto 88px auto" }}
    >
      {/* Row 0 */}
      <StateBox label="Trống" sub="Không có người" color="neutral" />
      <HArrow dir="right" label="Phát hiện người" />
      <StateBox label="Chờ vào" sub="Đang xác nhận vào" color="pending" />

      {/* Row 1: vertical arrows + center hint */}
      <VArrow
        dir="up"
        label={`${confirm_exit_time}s`}
        sublabel="confirm_exit_time"
      />
      <div className="flex items-center justify-center">
        <span className="text-center text-[10px] leading-snug text-muted-foreground/60">
          grace<br />{pending_enter_miss_grace_time}s
        </span>
      </div>
      <VArrow
        dir="down"
        label={`${confirm_enter_time}s`}
        sublabel="confirm_enter_time"
      />

      {/* Row 2 */}
      <StateBox label="Chờ ra" sub="Đang xác nhận ra" color="pending" />
      <HArrow dir="left" label="Mất dấu người" />
      <StateBox label="Có người" sub="Đã xác nhận" color="occupied" />
    </div>
  )
}

// ── Config card ───────────────────────────────────────────────────────────────

function ConfigCard({
  config,
  onSaved,
}: {
  config: ZoneStateMachineConfig
  onSaved: () => void
}) {
  const [draft, setDraft] = useState<ZoneStateMachineConfig>({ ...config })
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  function startEdit() { setDraft({ ...config }); setEditing(true) }
  function cancel() { setEditing(false) }
  async function save() {
    setSaving(true)
    try {
      const response = await zoneStateMachineApi.update(draft)
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <FieldLabel
              label="Confirm enter time (s)"
              desc="Thời gian chờ để xác nhận người đã vào zone"
            />
            {editing
              ? <NumField value={draft.confirm_enter_time} onChange={(val) => setDraft((p) => ({ ...p, confirm_enter_time: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.confirm_enter_time}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel
              label="Confirm exit time (s)"
              desc="Thời gian chờ để xác nhận người đã rời zone"
            />
            {editing
              ? <NumField value={draft.confirm_exit_time} onChange={(val) => setDraft((p) => ({ ...p, confirm_exit_time: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.confirm_exit_time}</div>
            }
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel
              label="Pending enter grace time (s)"
              desc="Thời gian bỏ qua khi mất dấu lúc đang chờ xác nhận vào"
            />
            {editing
              ? <NumField value={draft.pending_enter_miss_grace_time} onChange={(val) => setDraft((p) => ({ ...p, pending_enter_miss_grace_time: val }))} />
              : <div className="flex h-8 items-center text-sm">{v.pending_enter_miss_grace_time}</div>
            }
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ZoneStateMachinePage() {
  const { data: config, isLoading, isError, refetch } = useZoneStateMachineConfig()
  const invalidateZoneStateMachine = useInvalidateZoneStateMachine()

  function handleSaved() {
    invalidateZoneStateMachine()
    refetch()
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-40" />
        <Skeleton className="h-80" />
      </div>
    )
  }

  if (isError || !config) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Zone State Machine</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Không tải được cấu hình Zone State Machine.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <ConfigCard config={config} onSaved={handleSaved} />

      <Card>
        <CardHeader>
          <CardTitle>Sơ đồ trạng thái</CardTitle>
        </CardHeader>
        <CardContent>
          <StateDiagram config={config} />
        </CardContent>
      </Card>
    </div>
  )
}
