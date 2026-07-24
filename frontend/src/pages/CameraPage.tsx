import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react"
import { useParams, useNavigate } from "react-router-dom"
import { Crosshair, MapPin, Navigation, Pencil, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import { useCamera } from "@/hooks/use-camera"
import { useInvalidateCameras } from "@/hooks/use-cameras"
import { camerasApi, type Camera, type Zone } from "@/api/cameras.api"
import { cameraCalibrationApi } from "@/api/camera-calibration.api"
import { uartApi } from "@/api/uart.api"
import { useRobotHeartbeats } from "@/hooks/use-robot-heartbeats"
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
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

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

const ZONE_COLORS = [
  "#0ea5e9", "#10b981", "#f59e0b", "#f43f5e", "#8b5cf6", "#ec4899",
]

function projectPixelToWorld(
  point: [number, number],
  homography: number[][],
): [number, number] {
  if (
    homography.length !== 3
    || homography.some(
      (row) => row.length !== 3 || row.some((value) => !Number.isFinite(value)),
    )
  ) {
    throw new Error("Ma trận homography của camera không hợp lệ")
  }

  const [pixelX, pixelY] = point
  const denominator =
    homography[2][0] * pixelX
    + homography[2][1] * pixelY
    + homography[2][2]
  if (!Number.isFinite(denominator) || Math.abs(denominator) < 1e-9) {
    throw new Error("Không thể chiếu điểm pixel bằng ma trận homography")
  }

  const worldX = (
    homography[0][0] * pixelX
    + homography[0][1] * pixelY
    + homography[0][2]
  ) / denominator
  const worldY = (
    homography[1][0] * pixelX
    + homography[1][1] * pixelY
    + homography[1][2]
  ) / denominator
  if (!Number.isFinite(worldX) || !Number.isFinite(worldY)) {
    throw new Error("Tọa độ đích sau khi chiếu không hợp lệ")
  }

  return [worldX, worldY]
}

function generateMoveId(): number {
  return Math.floor(Math.random() * 256)
}

export function CameraPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const invalidateCameras = useInvalidateCameras()
  const { data: camera, isLoading, isError } = useCamera(id!)
  const { snapshot: robotSnapshot } = useRobotHeartbeats()

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
  const [isPickingServicePoint, setIsPickingServicePoint] = useState(false)
  const [draftServicePoint, setDraftServicePoint] = useState<[number, number] | null>(null)
  const [servicePointRobotId, setServicePointRobotId] = useState("")
  const [isMovingToServicePoint, setIsMovingToServicePoint] = useState(false)
  const onlineRobots = robotSnapshot?.robots.filter((robot) => robot.online) ?? []
  const selectedServicePointRobotId = onlineRobots.some(
    (robot) => String(robot.robot_id) === servicePointRobotId,
  )
    ? servicePointRobotId
    : onlineRobots[0] ? String(onlineRobots[0].robot_id) : ""

  // Zone name editing
  const [draftZoneName, setDraftZoneName]     = useState("")
  const [zoneNameError, setZoneNameError]     = useState("")

  // New-zone naming dialog
  const [pendingPoints, setPendingPoints]           = useState<number[][] | null>(null)
  const [zoneNameDialogOpen, setZoneNameDialogOpen] = useState(false)
  const [pendingZoneName, setPendingZoneName]       = useState("")
  const [pendingZoneNameError, setPendingZoneNameError] = useState("")

  // Zone delete dialog
  const [deletingZoneId, setDeletingZoneId] = useState<string | null>(null)
  const [isDeletingZone, setIsDeletingZone] = useState(false)
  const videoPanelRef = useRef<HTMLDivElement>(null)
  const [videoPanelHeight, setVideoPanelHeight] = useState<number | null>(null)

  const isInteracting = isAddingZone || isEditingVertices
  const displayZones  = isEditingVertices ? draftZones : (camera?.zones ?? [])

  useEffect(() => {
    const element = videoPanelRef.current
    if (!element) return

    const updateHeight = () => {
      setVideoPanelHeight(Math.round(element.getBoundingClientRect().height))
    }

    updateHeight()
    const observer = new ResizeObserver(updateHeight)
    observer.observe(element)
    return () => observer.disconnect()
  }, [camera])

  useEffect(() => {
    setEditOpen(false)
    setDeleteOpen(false)
    setIsAddingZone(false)
    setIsEditingVertices(false)
    setSelectedZoneIndex(null)
    setDraftZones([])
    setIsConfirming(false)
    setIsPickingServicePoint(false)
    setDraftServicePoint(null)
    setDraftZoneName("")
    setZoneNameError("")
    setPendingPoints(null)
    setZoneNameDialogOpen(false)
    setPendingZoneName("")
    setPendingZoneNameError("")
    setDeletingZoneId(null)
    setIsDeletingZone(false)
  }, [id])

  function invalidateCamera() {
    queryClient.invalidateQueries({ queryKey: ["cameras", id] })
  }

  // ── Camera actions ─────────────────────────────────────────────────────────

  async function handleDeleteCamera() {
    setIsDeleting(true)
    try {
      const response = await camerasApi.delete(id!)
      toast.success(response.message)
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
    setIsPickingServicePoint(false)
    setDraftServicePoint(zone?.service_point ?? null)
  }

  const handleZoneSelect = useCallback((index: number) => {
    if (index === selectedZoneIndex) return

    setSelectedZoneIndex(index)

    if (!isEditingVertices) return

    const zone = draftZones[index]
    setDraftZoneName(zone?.name ?? "")
    setZoneNameError("")
    setIsPickingServicePoint(false)
    setDraftServicePoint(zone?.service_point ?? null)
  }, [selectedZoneIndex, isEditingVertices, draftZones])

  function handleCancel() {
    setIsAddingZone(false)
    setIsEditingVertices(false)
    setSelectedZoneIndex(null)
    setDraftZones([])
    setDraftZoneName("")
    setZoneNameError("")
    setIsPickingServicePoint(false)
    setDraftServicePoint(null)
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
    if (!draftServicePoint) {
      toast.error("Vui lòng chọn điểm phục vụ trước khi lưu zone")
      setIsPickingServicePoint(true)
      return
    }

    setIsConfirming(true)
    try {
      const updatedZones = draftZones.map((z, i) =>
        i === selectedZoneIndex
          ? { ...z, name: trimmedName, service_point: draftServicePoint }
          : z,
      )
      const response = await camerasApi.update(id!, { zones: updatedZones })

      // Cập nhật cache ngay lập tức trước khi thoát edit mode
      // để displayZones không flash về dữ liệu cũ trong khi chờ refetch
      queryClient.setQueryData<Camera>(["cameras", id], response.data)

      setIsEditingVertices(false)
      setSelectedZoneIndex(null)
      setDraftZones([])
      setDraftZoneName("")
      setZoneNameError("")
      setIsPickingServicePoint(false)
      setDraftServicePoint(null)
      toast.success(response.message)
      invalidateCameras()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Cập nhật zone thất bại")
    } finally {
      setIsConfirming(false)
    }
  }

  const handleZoneAdd = useCallback((points: number[][]) => {
    setIsAddingZone(false)
    setPendingPoints(points)
    setPendingZoneName("")
    setZoneNameDialogOpen(true)
  }, [])

  const handleZonePointsChange = useCallback((index: number, points: number[][]) => {
    setDraftZones((prev) =>
      prev.map((z, i) => (i === index ? { ...z, points: points as [number, number][] } : z)),
    )
  }, [])

  const handleServicePointChange = useCallback((point: [number, number]) => {
    setDraftServicePoint(point)
    setIsPickingServicePoint(false)
    if (selectedZoneIndex !== null) {
      setDraftZones((zones) =>
        zones.map((zone, index) =>
          index === selectedZoneIndex
            ? { ...zone, service_point: point }
            : zone,
        ),
      )
    }
  }, [selectedZoneIndex])

  async function handleMoveToServicePoint() {
    if (!draftServicePoint) {
      toast.error("Vui lòng chọn điểm phục vụ trên video")
      return
    }
    if (!selectedServicePointRobotId) {
      toast.error("Không có robot online để nhận lệnh")
      return
    }

    setIsMovingToServicePoint(true)
    try {
      const calibration = await cameraCalibrationApi.get(id!)
      if (!calibration) {
        throw new Error("Camera chưa có ma trận homography đã áp dụng")
      }

      const [x, y] = projectPixelToWorld(
        draftServicePoint,
        calibration.homography,
      )
      if (x < -327.68 || x > 327.67 || y < -327.68 || y > 327.67) {
        throw new Error("Tọa độ đích nằm ngoài phạm vi giao thức")
      }

      const result = await uartApi.moveToPoint({
        robot_id: Number(selectedServicePointRobotId),
        move_id: generateMoveId(),
        x,
        y,
        theta: 0,
      })
      toast.success(
        `Robot #${result.robot_id} đã nhận điểm (${x.toFixed(2)}, ${y.toFixed(2)})`,
      )
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Không thể gửi lệnh di chuyển tới điểm phục vụ",
      )
    } finally {
      setIsMovingToServicePoint(false)
    }
  }

  function handleSaveNewZone() {
    if (!pendingPoints || !camera) return
    const trimmedName = pendingZoneName.trim()
    if (!trimmedName) { setPendingZoneNameError("Tên zone không được để trống"); return }
    const isDuplicate = camera.zones.some((z) => z.name === trimmedName)
    if (isDuplicate) { setPendingZoneNameError("Tên zone đã tồn tại"); return }

    const newZone: Zone = {
      name: trimmedName,
      points: pendingPoints as [number, number][],
      service_point: null,
    }
    setDraftZones([...camera.zones, newZone])
    setSelectedZoneIndex(camera.zones.length)
    setDraftZoneName(trimmedName)
    setZoneNameError("")
    setDraftServicePoint(null)
    setIsEditingVertices(true)
    setIsPickingServicePoint(true)
    setZoneNameDialogOpen(false)
    setPendingPoints(null)
    setPendingZoneName("")
    setPendingZoneNameError("")
    toast.info("Chọn điểm phục vụ trên video rồi nhấn Xác nhận")
  }

  async function handleDeleteZone() {
    if (!camera || !deletingZoneId) return
    setIsDeletingZone(true)
    try {
      const updatedZones = camera.zones.filter((z) => z.id !== deletingZoneId)
      const response = await camerasApi.update(id!, { zones: updatedZones })
      toast.success(response.message)
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
    selectedZoneIndex !== null
      ? (
          (isEditingVertices ? draftZones : camera.zones)[selectedZoneIndex]?.name
          ?? "zone"
        )
      : "zone"
  const selectedZoneColor = ZONE_COLORS[
    (selectedZoneIndex ?? 0) % ZONE_COLORS.length
  ]

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
        <Card>
          <CardHeader>
            <CardTitle>Hiển thị camera</CardTitle>
          </CardHeader>

          <CardContent className="p-0">
            <div className="flex flex-col overflow-hidden md:grid md:grid-cols-[minmax(0,1fr)_16rem]">

              {/* Video */}
              <div
                ref={videoPanelRef}
                className="relative aspect-video w-full min-w-0 self-start overflow-hidden bg-black"
              >
                <CameraPreview
                  src={camera.webrtc_address ?? ""}
                  zones={displayZones}
                  isAddingZone={isAddingZone}
                  isEditingVertices={isEditingVertices}
                  isPickingServicePoint={isPickingServicePoint}
                  selectedZoneIndex={selectedZoneIndex}
                  servicePoint={draftServicePoint}
                  onZoneAdd={handleZoneAdd}
                  onZonePointsChange={handleZonePointsChange}
                  onZoneSelect={handleZoneSelect}
                  onServicePointChange={handleServicePointChange}
                />
              </div>

              {/* Zone panel */}
              <div
                className="flex h-[475px] min-h-0 w-full flex-col overflow-hidden border-t md:h-[var(--camera-video-height)] md:w-auto md:border-l md:border-t-0"
                style={
                  {
                    "--camera-video-height": videoPanelHeight
                      ? `${videoPanelHeight}px`
                      : "auto",
                  } as CSSProperties
                }
              >
                {isInteracting ? (
                  <>
                    {/* Header */}
                    <div className="flex h-14 shrink-0 items-center border-b px-4">
                      <p className="text-sm font-medium">
                        {isAddingZone
                          ? "Thêm zone"
                          : isPickingServicePoint
                            ? `Chọn điểm phục vụ: ${editingZoneName}`
                            : `Đang sửa: ${editingZoneName}`}
                      </p>
                    </div>

                    {/* Content */}
                    <div className="min-h-0 w-full min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
                      <div className="box-border flex w-full max-w-full min-w-0 flex-col gap-4 overflow-x-hidden p-4">
                        {isEditingVertices && (
                          <>
                            {/* Zone name */}
                            <div className="flex min-w-0 flex-col gap-1.5">
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

                            {/* Service point prototype */}
                            <div className="flex min-w-0 flex-col gap-2.5">
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-1.5">
                                  <MapPin
                                    className="size-3.5"
                                    style={{ color: selectedZoneColor }}
                                  />
                                  <p className="text-xs font-medium">Điểm phục vụ</p>
                                </div>
                                <Badge variant="outline" className="text-[10px]">
                                  UI thử nghiệm
                                </Badge>
                              </div>

                              {draftServicePoint ? (
                                <div
                                  className="flex items-center gap-2 rounded-md border px-3 py-2"
                                  style={{
                                    borderColor: `${selectedZoneColor}4d`,
                                    backgroundColor: `${selectedZoneColor}1a`,
                                  }}
                                >
                                  <span
                                    className="size-2 shrink-0 rounded-full"
                                    style={{ backgroundColor: selectedZoneColor }}
                                  />
                                  <span className="text-xs text-muted-foreground">Pixel</span>
                                  <span className="ml-auto text-xs">
                                    X {draftServicePoint[0]} · Y {draftServicePoint[1]}
                                  </span>
                                </div>
                              ) : (
                                <div className="rounded-md border border-dashed px-3 py-3 text-center text-xs text-muted-foreground">
                                  Chưa chọn điểm trên video.
                                </div>
                              )}

                              <Select
                                value={selectedServicePointRobotId}
                                onValueChange={setServicePointRobotId}
                              >
                                <SelectTrigger className="w-full">
                                  <SelectValue
                                    placeholder={
                                      onlineRobots.length === 0
                                        ? "Không có robot online"
                                        : "Chọn robot"
                                    }
                                  />
                                </SelectTrigger>
                                <SelectContent position="popper">
                                  {onlineRobots.map((robot) => (
                                    <SelectItem
                                      key={robot.robot_id}
                                      value={String(robot.robot_id)}
                                    >
                                      <span className="flex items-center gap-2">
                                        <span className="size-2 rounded-full bg-emerald-500" />
                                        Robot #{robot.robot_id}
                                      </span>
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>

                              <Button
                                size="sm"
                                variant={isPickingServicePoint ? "secondary" : "outline"}
                                className="w-full"
                                onClick={() => setIsPickingServicePoint((current) => !current)}
                              >
                                <Crosshair />
                                {isPickingServicePoint
                                  ? "Dừng chọn điểm"
                                  : draftServicePoint ? "Chọn lại điểm" : "Chọn điểm trên video"}
                              </Button>
                              <Button
                                size="sm"
                                className="w-full"
                                disabled={
                                  !draftServicePoint
                                  || !selectedServicePointRobotId
                                  || isMovingToServicePoint
                                }
                                onClick={handleMoveToServicePoint}
                              >
                                <Navigation />
                                {isMovingToServicePoint
                                  ? "Đang gửi lệnh..."
                                  : "Test chuyển đến điểm"}
                              </Button>
                            </div>

                            <Separator />
                          </>
                        )}

                        {/* Instruction */}
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          {isAddingZone
                            ? "Click lên video để thêm từng điểm. Double-click để hoàn tất polygon."
                            : isPickingServicePoint
                              ? "Click một vị trí trên video để đặt điểm phục vụ cho zone."
                              : draftServicePoint
                                ? "Kéo marker để đổi điểm phục vụ; kéo các đỉnh để chỉnh zone."
                                : "Kéo các điểm trên video để chỉnh lại vị trí của zone."}
                        </p>
                      </div>
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
                    <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
                      <span className="text-sm font-medium">Zones ({camera.zones.length})</span>
                      <Button size="sm" variant="outline" onClick={() => setIsAddingZone(true)}>
                        <Plus />
                        Thêm
                      </Button>
                    </div>

                    {/* Zone list */}
                    <ScrollArea className="min-h-0 w-full min-w-0 flex-1">
                      <ul className="w-full min-w-0 py-1">
                        {camera.zones.length === 0 ? (
                          <li className="px-4 py-6 text-center text-xs text-muted-foreground">
                            Chưa có zone nào.
                          </li>
                        ) : (
                          camera.zones.map((zone, index) => (
                            <li
                              key={zone.id ?? index}
                              className="min-w-0 overflow-hidden"
                            >
                              <div className="flex items-center gap-2 overflow-hidden px-3 py-2.5 transition-colors hover:bg-muted/50">
                                <div className="flex flex-1 items-center gap-2 overflow-hidden">
                                  {/* Number badge */}
                                  <span
                                    className="flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                                    style={{ backgroundColor: ZONE_COLORS[index % ZONE_COLORS.length] }}
                                  >
                                    {index + 1}
                                  </span>
                                  <span className="truncate text-sm">{zone.name}</span>
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
                                  <Popover
                                    open={deletingZoneId === zone.id}
                                    onOpenChange={(open) => setDeletingZoneId(open ? (zone.id ?? null) : null)}
                                  >
                                    <PopoverTrigger asChild>
                                      <Button
                                        variant="outline"
                                        size="icon"
                                        className="size-7 text-destructive hover:text-destructive hover:bg-destructive/10 border-destructive/30"
                                      >
                                        <Trash2 className="size-3.5" />
                                      </Button>
                                    </PopoverTrigger>
                                    <PopoverContent align="end" className="w-56">
                                      <PopoverHeader>
                                        <PopoverTitle>Xóa zone</PopoverTitle>
                                        <PopoverDescription>
                                          Bạn có chắc muốn xóa{" "}
                                          <span className="font-medium text-foreground">"{zone.name}"</span>?
                                        </PopoverDescription>
                                      </PopoverHeader>
                                      <div className="flex justify-end gap-2">
                                        <Button size="sm" variant="outline" onClick={() => setDeletingZoneId(null)}>
                                          Hủy
                                        </Button>
                                        <Button size="sm" variant="destructive" disabled={isDeletingZone} onClick={handleDeleteZone}>
                                          {isDeletingZone ? "Đang xóa..." : "Xóa"}
                                        </Button>
                                      </div>
                                    </PopoverContent>
                                  </Popover>
                                </div>
                              </div>
                              {index < camera.zones.length - 1 && <Separator />}
                            </li>
                          ))
                        )}
                      </ul>
                    </ScrollArea>
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
            <Button disabled={!pendingZoneName.trim()} onClick={handleSaveNewZone}>
              Tiếp tục
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </>
  )
}
