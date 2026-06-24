import { useEffect, useRef, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import { useCamera } from "@/hooks/use-camera"
import { useInvalidateCameras } from "@/hooks/use-cameras"
import { camerasApi, type Camera, type Zone, type GoalPose } from "@/api/cameras.api"
import { EditCameraDialog } from "@/components/edit-camera-dialog"
import { CameraPreview } from "@/components/camera-preview"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"

function maskRtspPassword(url: string): string {
  return url.replace(/^(rtsp:\/\/[^:]+):([^@]+)@/, "$1:***@")
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="text-sm break-all">{value}</div>
    </div>
  )
}

function GoalPoseField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  disabled?: boolean
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
    <div className="flex items-center gap-2">
      <span className="w-5 shrink-0 text-xs font-mono font-medium text-muted-foreground">{label}</span>
      <Input
        type="number"
        step="0.01"
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
        disabled={disabled}
        className="h-7 text-xs [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
    </div>
  )
}

const ZONE_COLORS = [
  "#0ea5e9", "#10b981", "#f59e0b", "#f43f5e", "#8b5cf6", "#ec4899",
]

export function CameraPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const invalidateCameras = useInvalidateCameras()
  const { data: camera, isLoading, isError } = useCamera(id!)

  // Camera-level dialogs
  const [editOpen, setEditOpen]     = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  // Zone interaction
  const [isAddingZone, setIsAddingZone]           = useState(false)
  const [isEditingVertices, setIsEditingVertices] = useState(false)
  const [selectedZoneIndex, setSelectedZoneIndex] = useState<number | null>(null)
  const [draftZones, setDraftZones]               = useState<Zone[]>([])
  const [isConfirming, setIsConfirming]           = useState(false)

  // Goal pose + name editing
  const [draftZoneName, setDraftZoneName]     = useState("")
  const [zoneNameError, setZoneNameError]     = useState("")
  const [draftGoalPose, setDraftGoalPose]     = useState<GoalPose>({ x: 0, y: 0, theta: 0 })
  const [realtimeGoalPose, setRealtimeGoalPose] = useState(false)

  // New-zone naming dialog
  const [pendingPoints, setPendingPoints]           = useState<number[][] | null>(null)
  const [zoneNameDialogOpen, setZoneNameDialogOpen] = useState(false)
  const [pendingZoneName, setPendingZoneName]       = useState("")
  const [pendingZoneNameError, setPendingZoneNameError] = useState("")
  const [isSavingZone, setIsSavingZone]             = useState(false)

  // Zone delete dialog
  const [deletingZoneId, setDeletingZoneId] = useState<string | null>(null)
  const [isDeletingZone, setIsDeletingZone] = useState(false)

  const isInteracting = isAddingZone || isEditingVertices
  const displayZones  = isEditingVertices ? draftZones : (camera?.zones ?? [])

  function invalidateCamera() {
    queryClient.invalidateQueries({ queryKey: ["cameras", id] })
  }

  // ── Camera actions ─────────────────────────────────────────────────────────

  async function handleDeleteCamera() {
    setIsDeleting(true)
    try {
      await camerasApi.delete(id!)
      toast.success(`Đã xóa camera "${camera?.name}"`)
      invalidateCameras()
      navigate("/")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Xóa thất bại")
    } finally {
      setIsDeleting(false)
      setDeleteOpen(false)
    }
  }

  // ── Zone actions ───────────────────────────────────────────────────────────

  function handleStartEdit(index: number) {
    const zone = camera?.zones[index]
    setSelectedZoneIndex(index)
    setDraftZones([...(camera?.zones ?? [])])
    setIsEditingVertices(true)
    setDraftZoneName(zone?.name ?? "")
    setZoneNameError("")
    setDraftGoalPose(zone?.goal_pose ?? { x: 0, y: 0, theta: 0 })
    setRealtimeGoalPose(false)
  }

  function handleCancel() {
    setIsAddingZone(false)
    setIsEditingVertices(false)
    setSelectedZoneIndex(null)
    setDraftZones([])
    setDraftZoneName("")
    setZoneNameError("")
  }

  async function handleConfirmEdit() {
    if (!isEditingVertices || selectedZoneIndex === null) return

    const trimmedName = draftZoneName.trim()
    if (!trimmedName) {
      setZoneNameError("Tên zone không được để trống")
      return
    }
    const isDuplicate = camera!.zones.some((z, i) => i !== selectedZoneIndex && z.name === trimmedName)
    if (isDuplicate) {
      setZoneNameError("Tên zone đã tồn tại")
      return
    }

    setIsConfirming(true)
    try {
      const updatedZones = draftZones.map((z, i) =>
        i === selectedZoneIndex ? { ...z, name: trimmedName, goal_pose: draftGoalPose } : z,
      )
      await camerasApi.update(id!, { zones: updatedZones })

      // Cập nhật cache ngay lập tức trước khi thoát edit mode
      // để displayZones không flash về dữ liệu cũ trong khi chờ refetch
      queryClient.setQueryData<Camera>(["cameras", id], (old) =>
        old ? { ...old, zones: updatedZones } : old,
      )

      setIsEditingVertices(false)
      setSelectedZoneIndex(null)
      setDraftZones([])
      setDraftZoneName("")
      setZoneNameError("")
      toast.success("Đã cập nhật zone")
      invalidateCameras()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Cập nhật zone thất bại")
    } finally {
      setIsConfirming(false)
    }
  }

  function handleZoneAdd(points: number[][]) {
    setIsAddingZone(false)
    setPendingPoints(points)
    setPendingZoneName("")
    setZoneNameDialogOpen(true)
  }

  function handleZonePointsChange(index: number, points: number[][]) {
    setDraftZones((prev) =>
      prev.map((z, i) => (i === index ? { ...z, points: points as [number, number][] } : z)),
    )
  }

  async function handleSaveNewZone() {
    if (!pendingPoints || !camera) return
    const trimmedName = pendingZoneName.trim()
    if (!trimmedName) { setPendingZoneNameError("Tên zone không được để trống"); return }
    const isDuplicate = camera.zones.some((z) => z.name === trimmedName)
    if (isDuplicate) { setPendingZoneNameError("Tên zone đã tồn tại"); return }

    setIsSavingZone(true)
    try {
      const newZone: Zone = {
        name: trimmedName,
        points: pendingPoints as [number, number][],
        goal_pose: null,
      }
      await camerasApi.update(id!, { zones: [...camera.zones, newZone] })
      toast.success("Đã thêm zone")
      invalidateCamera()
      invalidateCameras()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thêm zone thất bại")
    } finally {
      setIsSavingZone(false)
      setZoneNameDialogOpen(false)
      setPendingPoints(null)
      setPendingZoneName("")
      setPendingZoneNameError("")
    }
  }

  async function handleDeleteZone() {
    if (!camera || !deletingZoneId) return
    setIsDeletingZone(true)
    try {
      const updatedZones = camera.zones.filter((z) => z.id !== deletingZoneId)
      await camerasApi.update(id!, { zones: updatedZones })
      toast.success("Đã xóa zone")
      invalidateCamera()
      invalidateCameras()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Xóa zone thất bại")
    } finally {
      setIsDeletingZone(false)
      setDeletingZoneId(null)
    }
  }

  // ── Loading / error ────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-48" />
        <Skeleton className="h-[500px]" />
      </div>
    )
  }

  if (isError || !camera) {
    return <p className="text-sm text-muted-foreground">Không tìm thấy camera.</p>
  }

  const editingZoneName =
    selectedZoneIndex !== null ? (camera.zones[selectedZoneIndex]?.name ?? "zone") : "zone"

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <>
      <div className="flex flex-col gap-6">

        {/* Camera info */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Thông tin camera</CardTitle>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
                  <Pencil />
                  Sửa
                </Button>
                <Button variant="destructive" size="sm" onClick={() => setDeleteOpen(true)}>
                  <Trash2 />
                  Xóa
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <InfoRow label="Tên" value={camera.name} />
              <InfoRow
                label="Trạng thái"
                value={
                  <Badge variant={camera.enabled ? "default" : "secondary"}>
                    {camera.enabled ? "Enabled" : "Disabled"}
                  </Badge>
                }
              />
              <InfoRow label="Nguồn RTSP" value={maskRtspPassword(camera.stream.source)} />
              <InfoRow label="Protocol" value={camera.stream.protocol.toUpperCase()} />
              <InfoRow label="On demand" value={camera.stream.on_demand ? "Có" : "Không"} />
              {camera.webrtc_address && (
                <InfoRow
                  label="WebRTC"
                  value={
                    <a
                      href={camera.webrtc_address}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary underline underline-offset-4"
                    >
                      {camera.webrtc_address}
                    </a>
                  }
                />
              )}
            </div>
          </CardContent>
        </Card>

        {/* Video + zone management */}
        <Card className="pb-0">
          <CardHeader>
            <CardTitle>Hiển thị camera</CardTitle>
          </CardHeader>

          <CardContent className="p-0">
            <div className="flex flex-col md:flex-row md:h-[500px] overflow-hidden">

              {/* Video */}
              <div className="relative h-[260px] md:h-auto md:flex-1 overflow-hidden">
                <CameraPreview
                  src={camera.webrtc_address ?? ""}
                  zones={displayZones}
                  isAddingZone={isAddingZone}
                  isEditingVertices={isEditingVertices}
                  selectedZoneIndex={selectedZoneIndex}
                  onZoneAdd={handleZoneAdd}
                  onZonePointsChange={handleZonePointsChange}
                  onZoneSelect={setSelectedZoneIndex}
                />
              </div>

              {/* Zone panel */}
              <div className="flex shrink-0 flex-col border-t md:border-t-0 md:border-l w-full md:w-64 max-h-[300px] md:max-h-none">
                {isInteracting ? (
                  <>
                    {/* Header */}
                    <div className="border-b px-4 py-3">
                      <p className="text-sm font-medium">
                        {isAddingZone ? "Thêm zone" : `Đang sửa: ${editingZoneName}`}
                      </p>
                    </div>

                    {/* Scrollable content */}
                    <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
                      {isEditingVertices && (
                        <>
                          {/* Zone name */}
                          <div className="flex flex-col gap-1.5">
                            <p className="text-xs font-medium">Tên zone</p>
                            <Input
                              value={draftZoneName}
                              onChange={(e) => { setDraftZoneName(e.target.value); setZoneNameError("") }}
                              className="h-7 text-xs"
                              placeholder="Tên zone"
                            />
                            {zoneNameError && (
                              <p className="text-xs text-destructive">{zoneNameError}</p>
                            )}
                          </div>

                          {/* Goal pose fields */}
                          <div className="flex flex-col gap-2">
                            <p className="text-xs font-medium">Goal Pose</p>
                            <GoalPoseField
                              label="X"
                              value={draftGoalPose.x}
                              onChange={(v) => setDraftGoalPose((p) => ({ ...p, x: v }))}
                              disabled={realtimeGoalPose}
                            />
                            <GoalPoseField
                              label="Y"
                              value={draftGoalPose.y}
                              onChange={(v) => setDraftGoalPose((p) => ({ ...p, y: v }))}
                              disabled={realtimeGoalPose}
                            />
                            <GoalPoseField
                              label="θ"
                              value={draftGoalPose.theta}
                              onChange={(v) => setDraftGoalPose((p) => ({ ...p, theta: v }))}
                              disabled={realtimeGoalPose}
                            />
                          </div>

                          {/* Realtime switch */}
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs text-muted-foreground leading-snug">
                              Nhận giá trị realtime
                            </span>
                            <Switch
                              checked={realtimeGoalPose}
                              onCheckedChange={setRealtimeGoalPose}
                            />
                          </div>

                          <Separator />
                        </>
                      )}

                      {/* Instruction */}
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {isAddingZone
                          ? "Click lên video để thêm từng điểm. Double-click để hoàn tất polygon."
                          : "Kéo các điểm trên video để chỉnh lại vị trí của zone."}
                      </p>
                    </div>

                    {/* Pinned buttons */}
                    <div className="border-t p-4 flex flex-col gap-2">
                      {isEditingVertices && (
                        <Button size="sm" disabled={isConfirming} onClick={handleConfirmEdit}>
                          {isConfirming ? "Đang lưu..." : "Xác nhận"}
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={handleCancel}>
                        Hủy
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    {/* Normal header */}
                    <div className="flex items-center justify-between border-b px-4 py-3">
                      <span className="text-sm font-medium">Zones ({camera.zones.length})</span>
                      <Button size="sm" variant="outline" onClick={() => setIsAddingZone(true)}>
                        <Plus />
                        Thêm
                      </Button>
                    </div>

                    {/* Zone list */}
                    <ul className="flex-1 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/40">
                      {camera.zones.length === 0 ? (
                        <li className="px-4 py-6 text-center text-xs text-muted-foreground">
                          Chưa có zone nào.
                        </li>
                      ) : (
                        camera.zones.map((zone, index) => (
                          <li
                            key={zone.id ?? index}
                            className="flex items-center justify-between px-3 py-2.5 transition-colors hover:bg-muted/50"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              {/* Number badge */}
                              <span
                                className="flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                                style={{ backgroundColor: ZONE_COLORS[index % ZONE_COLORS.length] }}
                              >
                                {index + 1}
                              </span>
                              <span className="text-sm truncate">{zone.name}</span>
                            </div>
                            <div className="flex shrink-0 items-center gap-1">
                              <Button
                                variant="outline"
                                size="icon"
                                className="size-7"
                                onClick={() => handleStartEdit(index)}
                              >
                                <Pencil className="size-3.5" />
                              </Button>
                              <Button
                                variant="outline"
                                size="icon"
                                className="size-7 text-destructive hover:text-destructive hover:bg-destructive/10 border-destructive/30"
                                onClick={() => setDeletingZoneId(zone.id ?? null)}
                              >
                                <Trash2 className="size-3.5" />
                              </Button>
                            </div>
                          </li>
                        ))
                      )}
                    </ul>
                  </>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Edit camera */}
      <EditCameraDialog camera={camera} open={editOpen} onOpenChange={setEditOpen} />

      {/* Delete camera */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Xóa camera</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Bạn có chắc muốn xóa camera{" "}
            <span className="font-medium text-foreground">"{camera.name}"</span>?
            Hành động này không thể hoàn tác.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>Hủy</Button>
            <Button variant="destructive" disabled={isDeleting} onClick={handleDeleteCamera}>
              {isDeleting ? "Đang xóa..." : "Xóa"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Name new zone */}
      <Dialog
        open={zoneNameDialogOpen}
        onOpenChange={(open) => {
          if (!open) { setZoneNameDialogOpen(false); setPendingPoints(null); setPendingZoneName(""); setPendingZoneNameError("") }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Đặt tên zone</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium">Tên zone</label>
            <Input
              autoFocus
              placeholder="VD: Cửa ra vào"
              value={pendingZoneName}
              onChange={(e) => { setPendingZoneName(e.target.value); setPendingZoneNameError("") }}
              onKeyDown={(e) => { if (e.key === "Enter") handleSaveNewZone() }}
            />
            {pendingZoneNameError && (
              <p className="text-xs text-destructive">{pendingZoneNameError}</p>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => { setZoneNameDialogOpen(false); setPendingPoints(null); setPendingZoneName(""); setPendingZoneNameError("") }}
            >
              Hủy
            </Button>
            <Button disabled={!pendingZoneName.trim() || isSavingZone} onClick={handleSaveNewZone}>
              {isSavingZone ? "Đang lưu..." : "Lưu"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete zone */}
      <Dialog
        open={deletingZoneId !== null}
        onOpenChange={(open) => { if (!open) setDeletingZoneId(null) }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Xóa zone</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Bạn có chắc muốn xóa zone{" "}
            <span className="font-medium text-foreground">
              "{camera.zones.find((z) => z.id === deletingZoneId)?.name}"
            </span>?
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingZoneId(null)}>Hủy</Button>
            <Button variant="destructive" disabled={isDeletingZone} onClick={handleDeleteZone}>
              {isDeletingZone ? "Đang xóa..." : "Xóa"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
