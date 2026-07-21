import { useEffect, useRef, useState, type CSSProperties } from "react"
import {
  Bot,
  Check,
  Crosshair,
  LocateFixed,
  MapPin,
  RotateCcw,
  Save,
} from "lucide-react"
import { useParams } from "react-router-dom"
import { toast } from "sonner"

import { CameraPreview } from "@/components/camera-preview"
import { CalibrationPointsOverlay } from "@/components/calibration-points-overlay"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { useCamera } from "@/hooks/use-camera"
import {
  createCalibrationPointPositions,
  type CalibrationPointPosition,
} from "@/lib/calibration-points"

const POINT_LAYOUT_OPTIONS = [
  { size: 2, label: "2×2 - 4 điểm" },
  { size: 3, label: "3×3 - 9 điểm" },
  { size: 4, label: "4×4 - 16 điểm" },
]

const MOCK_ROBOTS = [
  { id: "robot-1", name: "Robot #1", online: true, x: 1.25, y: 2.4 },
  { id: "robot-2", name: "Robot #2", online: true, x: 4.82, y: 1.13 },
  { id: "robot-3", name: "Robot #3", online: false, x: 0.65, y: 5.21 },
]

interface RobotCoordinateValue {
  robotId: string
  x: string
  y: string
  source: "manual" | "robot" | null
}

const EMPTY_ROBOT_COORDINATE: RobotCoordinateValue = {
  robotId: MOCK_ROBOTS[0].id,
  x: "",
  y: "",
  source: null,
}

export function CameraCalibrationPage() {
  const { id = "" } = useParams<{ id: string }>()
  const { data: camera, isLoading, isError } = useCamera(id)
  const [pointLayoutSize, setPointLayoutSize] = useState(2)
  const [points, setPoints] = useState<CalibrationPointPosition[]>(() =>
    createCalibrationPointPositions(2),
  )
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null)
  const [videoSize, setVideoSize] = useState<{
    width: number
    height: number
  } | null>(null)
  const [robotCoordinates, setRobotCoordinates] = useState<
    Record<string, RobotCoordinateValue>
  >({})
  const [savedRobotCoordinates, setSavedRobotCoordinates] = useState<
    Record<string, RobotCoordinateValue>
  >({})
  const videoPanelRef = useRef<HTMLDivElement>(null)
  const [videoPanelHeight, setVideoPanelHeight] = useState<number | null>(null)

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

  const selectedPoint =
    points.find((point) => point.id === selectedPointId) ?? null
  const selectedCoordinate = selectedPoint
    ? (robotCoordinates[selectedPoint.id] ?? EMPTY_ROBOT_COORDINATE)
    : null
  const selectedRobot = MOCK_ROBOTS.find(
    (robot) => robot.id === selectedCoordinate?.robotId,
  )
  const savedSelectedCoordinate = selectedPoint
    ? savedRobotCoordinates[selectedPoint.id]
    : undefined
  const isSelectedCoordinateSaved = Boolean(
    selectedCoordinate &&
      savedSelectedCoordinate &&
      selectedCoordinate.robotId === savedSelectedCoordinate.robotId &&
      selectedCoordinate.x === savedSelectedCoordinate.x &&
      selectedCoordinate.y === savedSelectedCoordinate.y,
  )
  const canSaveSelectedCoordinate = Boolean(
    selectedCoordinate?.x.trim() &&
      selectedCoordinate.y.trim() &&
      Number.isFinite(Number(selectedCoordinate.x)) &&
      Number.isFinite(Number(selectedCoordinate.y)),
  )

  function updateSelectedCoordinate(
    updates: Partial<RobotCoordinateValue>,
  ) {
    if (!selectedPoint) return
    setRobotCoordinates((current) => ({
      ...current,
      [selectedPoint.id]: {
        ...(current[selectedPoint.id] ?? EMPTY_ROBOT_COORDINATE),
        ...updates,
      },
    }))
  }

  function useCurrentRobotPosition() {
    if (!selectedRobot?.online) return
    updateSelectedCoordinate({
      x: selectedRobot.x.toFixed(2),
      y: selectedRobot.y.toFixed(2),
      source: "robot",
    })
  }

  function saveSelectedCoordinate() {
    if (!selectedPoint || !selectedCoordinate || !canSaveSelectedCoordinate) {
      toast.error("Vui lòng nhập tọa độ X và Y hợp lệ.")
      return
    }
    setSavedRobotCoordinates((current) => ({
      ...current,
      [selectedPoint.id]: { ...selectedCoordinate },
    }))
    toast.success(`Đã lưu tọa độ mock cho ${selectedPoint.label}.`)
  }

  function changePointLayout(value: string) {
    const size = Number(value)
    setPointLayoutSize(size)
    setPoints(createCalibrationPointPositions(size))
    setRobotCoordinates({})
    setSavedRobotCoordinates({})
    setSelectedPointId(null)
  }

  function resetPointPositions() {
    setPoints(createCalibrationPointPositions(pointLayoutSize))
    setSelectedPointId(null)
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-[560px] rounded-xl" />
      </div>
    )
  }

  if (isError || !camera) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Không tìm thấy camera.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>{camera.name}</CardTitle>
              <CardDescription>
                Camera calibration · ID: {camera.id}
              </CardDescription>
            </div>
            <Badge variant={camera.enabled ? "default" : "secondary"}>
              {camera.enabled ? "Enabled" : "Disabled"}
            </Badge>
          </div>
        </CardHeader>
      </Card>

      <Card className="gap-0 py-0">
        <CardHeader className="py-4">
          <CardTitle>Hiệu chỉnh tọa độ</CardTitle>
          <CardDescription>
            Chọn điểm ảnh tương ứng với vị trí robot trong hệ tọa độ thực.
          </CardDescription>
        </CardHeader>

        <CardContent className="p-0 pb-4">
          <div className="flex flex-col overflow-hidden lg:grid lg:grid-cols-[minmax(0,1fr)_20rem]">
            <div
              ref={videoPanelRef}
              className="relative aspect-video w-full min-w-0 self-start overflow-hidden bg-black"
            >
              <CameraPreview
                src={camera.webrtc_address ?? ""}
                onVideoSizeChange={setVideoSize}
              />
              <CalibrationPointsOverlay
                points={points}
                videoSize={videoSize}
                selectedPointId={selectedPointId}
                onPointsChange={setPoints}
                onPointSelect={setSelectedPointId}
              />
            </div>

            <aside
              className="flex min-h-0 w-full flex-col overflow-hidden border-t lg:h-[var(--calibration-video-height)] lg:w-auto lg:border-l lg:border-t-0"
              style={
                {
                  "--calibration-video-height": videoPanelHeight
                    ? `${videoPanelHeight}px`
                    : "auto",
                } as CSSProperties
              }
            >
              <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
                <div className="flex items-center gap-2">
                  <Crosshair className="size-4 text-muted-foreground" />
                  <p className="text-sm font-medium">Điểm calibration</p>
                </div>
                <Badge variant="secondary">{points.length} điểm</Badge>
              </div>

              <ScrollArea className="w-full min-w-0 lg:h-0 lg:min-h-0 lg:flex-1">
                <div className="box-border flex w-full max-w-full min-w-0 flex-col gap-5 overflow-x-hidden p-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Số điểm calibration
                  </label>
                  <Select
                    value={String(pointLayoutSize)}
                    onValueChange={changePointLayout}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent position="popper">
                      {POINT_LAYOUT_OPTIONS.map((option) => (
                        <SelectItem
                          key={option.size}
                          value={String(option.size)}
                        >
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex flex-col gap-2">
                  <p className="text-xs font-medium text-muted-foreground">
                    Danh sách điểm
                  </p>
                  <div className="grid grid-cols-4 gap-2">
                    {points.map((point) => (
                      <Button
                        key={point.id}
                        size="sm"
                        variant={
                          selectedPointId === point.id ? "default" : "outline"
                        }
                        onClick={() => setSelectedPointId(point.id)}
                      >
                        {point.label}
                      </Button>
                    ))}
                  </div>
                </div>

                {selectedPoint && selectedCoordinate ? (
                  <div className="min-h-[300px] overflow-hidden rounded-lg border">
                    <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <MapPin className="size-4 text-primary" />
                        <p className="text-sm font-medium">
                          {selectedPoint.label}
                        </p>
                      </div>
                      {videoSize && (
                        <Badge
                          variant="outline"
                          className="text-[10px] font-normal"
                        >
                          {Math.round(selectedPoint.x * videoSize.width)}, {" "}
                          {Math.round(selectedPoint.y * videoSize.height)} px
                        </Badge>
                      )}
                    </div>

                    <div className="flex flex-col gap-3 p-3">
                      <div className="flex flex-col gap-1.5">
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-medium">
                            Robot tham chiếu
                          </label>
                          <Badge variant="secondary" className="text-[10px]">
                            Mock data
                          </Badge>
                        </div>
                        <Select
                          value={selectedCoordinate.robotId}
                          onValueChange={(robotId) =>
                            updateSelectedCoordinate({ robotId, source: null })
                          }
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent position="popper">
                            {MOCK_ROBOTS.map((robot) => (
                              <SelectItem key={robot.id} value={robot.id}>
                                <span className="flex items-center gap-2">
                                  <span
                                    className={`size-2 rounded-full ${robot.online ? "bg-emerald-500" : "bg-zinc-400"}`}
                                  />
                                  {robot.name}
                                  {!robot.online && " · Offline"}
                                </span>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <div className="flex flex-col gap-1.5">
                          <label
                            htmlFor={`${selectedPoint.id}-robot-x`}
                            className="text-xs font-medium text-muted-foreground"
                          >
                            Tọa độ X (m)
                          </label>
                          <Input
                            id={`${selectedPoint.id}-robot-x`}
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            value={selectedCoordinate.x}
                            onChange={(event) =>
                              updateSelectedCoordinate({
                                x: event.target.value,
                                source: "manual",
                              })
                            }
                            onWheel={(event) => event.currentTarget.blur()}
                            className="tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                          />
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <label
                            htmlFor={`${selectedPoint.id}-robot-y`}
                            className="text-xs font-medium text-muted-foreground"
                          >
                            Tọa độ Y (m)
                          </label>
                          <Input
                            id={`${selectedPoint.id}-robot-y`}
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            value={selectedCoordinate.y}
                            onChange={(event) =>
                              updateSelectedCoordinate({
                                y: event.target.value,
                                source: "manual",
                              })
                            }
                            onWheel={(event) => event.currentTarget.blur()}
                            className="tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                          />
                        </div>
                      </div>

                      <div className="flex flex-col gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={!selectedRobot?.online}
                          onClick={useCurrentRobotPosition}
                          className="w-full"
                        >
                          <LocateFixed />
                          {selectedRobot?.online
                            ? "Lấy vị trí robot hiện tại"
                            : "Robot đang offline"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          disabled={
                            !canSaveSelectedCoordinate ||
                            isSelectedCoordinateSaved
                          }
                          onClick={saveSelectedCoordinate}
                          className="w-full"
                        >
                          {isSelectedCoordinateSaved ? <Check /> : <Save />}
                          {isSelectedCoordinateSaved
                            ? "Đã lưu tọa độ"
                            : "Lưu tọa độ"}
                        </Button>
                      </div>

                      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                        <Bot className="size-3.5 shrink-0" />
                        {selectedCoordinate.source === "robot"
                          ? `Đã lấy pose mock từ ${selectedRobot?.name}.`
                          : selectedCoordinate.source === "manual"
                            ? "Tọa độ đang được nhập thủ công."
                            : selectedRobot?.online
                              ? `Pose hiện tại: X ${selectedRobot.x.toFixed(2)} · Y ${selectedRobot.y.toFixed(2)} m`
                              : "Không có pose mới vì robot đang offline."}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="grid min-h-[300px] place-items-center rounded-lg border border-dashed bg-muted/20 p-6">
                    <div className="flex flex-col items-center gap-3 text-center">
                      <div className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
                        <MapPin className="size-4" />
                      </div>
                      <div className="space-y-1">
                        <p className="text-sm font-medium">
                          Chưa chọn điểm calibration
                        </p>
                        <p className="text-xs leading-5 text-muted-foreground">
                          Chọn một điểm trên stream hoặc trong danh sách để nhập
                          tọa độ robot.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
                </div>
              </ScrollArea>

              <div className="border-t bg-muted/30 p-4">
                <Button
                  variant="destructive"
                  className="w-full"
                  onClick={resetPointPositions}
                >
                  <RotateCcw />
                  Đặt lại vị trí các điểm
                </Button>
              </div>
            </aside>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
