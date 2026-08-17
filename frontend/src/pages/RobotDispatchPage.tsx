import { useEffect, useRef, useState } from "react"
import { Check, Pencil, RotateCcw, X } from "lucide-react"
import { toast } from "sonner"
import {
  robotDispatchApi,
  type RobotDispatchConfig,
} from "@/api/robot-dispatch.api"
import {
  useInvalidateRobotDispatch,
  useRobotDispatchConfig,
} from "@/hooks/use-robot-dispatch"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"

function NumberInput({
  value,
  min,
  step,
  integer = false,
  onChange,
}: {
  value: number
  min: number
  step: number
  integer?: boolean
  onChange: (value: number) => void
}) {
  const [raw, setRaw] = useState(String(value))
  const synced = useRef(value)

  useEffect(() => {
    if (synced.current !== value) {
      synced.current = value
      setRaw(String(value))
    }
  }, [value])

  const normalize = () => {
    const parsed = Number(raw)
    if (!Number.isFinite(parsed) || parsed < min || (integer && !Number.isInteger(parsed))) {
      setRaw(String(value))
      return
    }
    const normalized = String(parsed)
    setRaw(normalized)
    synced.current = parsed
    onChange(parsed)
  }

  return (
    <Input
      type="number"
      min={min}
      step={step}
      value={raw}
      onChange={(event) => setRaw(event.target.value)}
      onBlur={normalize}
      onWheel={(event) => event.currentTarget.blur()}
      className="h-8 w-28 text-right tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
    />
  )
}

function ToggleRow({
  label,
  description,
  value,
  editing,
  onChange,
}: {
  label: string
  description: string
  value: boolean
  editing: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="space-y-0.5">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs leading-snug text-muted-foreground">{description}</p>
      </div>
      {editing ? (
        <Switch checked={value} onCheckedChange={onChange} />
      ) : (
        <Badge variant={value ? "default" : "secondary"}>{value ? "Bật" : "Tắt"}</Badge>
      )}
    </div>
  )
}

function ConfigCard({ config, onSaved }: { config: RobotDispatchConfig; onSaved: () => void }) {
  const [draft, setDraft] = useState(config)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      const response = await robotDispatchApi.update(draft)
      toast.success(response.message)
      setEditing(false)
      onSaved()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Lưu cấu hình thất bại")
    } finally {
      setSaving(false)
    }
  }

  const value = editing ? draft : config

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle>Điều phối robot tự động</CardTitle>
            <CardDescription className="mt-1.5">
              Các thay đổi được lưu vào cấu hình và có hiệu lực khi Runtime khởi động lại.
            </CardDescription>
          </div>
          {editing ? (
            <div className="flex shrink-0 gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={saving}
                onClick={() => setEditing(false)}
              >
                <X /> Hủy
              </Button>
              <Button size="sm" disabled={saving} onClick={save}>
                <Check /> {saving ? "Đang lưu..." : "Lưu"}
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="blue"
              onClick={() => {
                setDraft(config)
                setEditing(true)
              }}
            >
              <Pencil /> Sửa
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <ToggleRow
          label="Bật auto-dispatch"
          description="Gửi TaskAssign hoặc TaskCancel theo kết quả zone state machine."
          value={value.enabled}
          editing={editing}
          onChange={(enabled) => setDraft((current) => ({ ...current, enabled }))}
        />
        <Separator />
        <ToggleRow
          label="Dùng Re-ID"
          description="Đưa kết quả Re-ID vào quyết định điều phối; chỉ bật được khi Re-ID đang hoạt động."
          value={value.use_reid}
          editing={editing}
          onChange={(use_reid) => setDraft((current) => ({ ...current, use_reid }))}
        />
        <Separator />
        <div className="flex items-center justify-between gap-4 py-3">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">Thời gian chờ ACK</p>
            <p className="text-xs text-muted-foreground">Số giây chờ robot xác nhận mỗi lệnh.</p>
          </div>
          {editing ? (
            <NumberInput
              value={value.ack_timeout_seconds}
              min={0.1}
              step={0.1}
              onChange={(ack_timeout_seconds) => setDraft((current) => ({ ...current, ack_timeout_seconds }))}
            />
          ) : (
            <span className="text-sm tabular-nums">{value.ack_timeout_seconds} giây</span>
          )}
        </div>
        <Separator />
        <div className="flex items-center justify-between gap-4 py-3">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">Số lần thử lại tối đa</p>
            <p className="text-xs text-muted-foreground">Số lần gửi lại khi lệnh chưa nhận được ACK.</p>
          </div>
          {editing ? (
            <NumberInput
              value={value.max_retries}
              min={1}
              step={1}
              integer
              onChange={(max_retries) => setDraft((current) => ({ ...current, max_retries }))}
            />
          ) : (
            <span className="text-sm tabular-nums">{value.max_retries} lần</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function RobotDispatchPage() {
  const configQuery = useRobotDispatchConfig()
  const invalidate = useInvalidateRobotDispatch()

  if (configQuery.isLoading) {
    return <Skeleton className="h-96 w-full" />
  }

  if (configQuery.isError || !configQuery.data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Không thể tải cấu hình robot dispatch</CardTitle>
          <CardDescription>Hãy kiểm tra kết nối API rồi thử lại.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={() => configQuery.refetch()}>
            <RotateCcw /> Thử lại
          </Button>
        </CardContent>
      </Card>
    )
  }

  return <ConfigCard config={configQuery.data} onSaved={invalidate} />
}
