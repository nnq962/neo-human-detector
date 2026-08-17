import type { CSSProperties } from "react"
import {
  Bot,
  Check,
  Crosshair,
  LocateFixed,
  MapPin,
  RotateCcw,
  Save,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  POINT_LAYOUT_OPTIONS,
  type CameraCalibrationController,
} from "@/hooks/use-camera-calibration"

interface CalibrationPointEditorProps {
  calibration: CameraCalibrationController
  panelHeight: number | null
}

export function CalibrationPointEditor({
  calibration,
  panelHeight,
}: CalibrationPointEditorProps) {
  const {
    pointLayoutSize,
    points,
    selectedPointId,
    setSelectedPointId,
    videoSize,
    selectedPoint,
    selectedCoordinate,
    selectedRobot,
    robots,
    robotSnapshot,
    robotsConnected,
    isSelectedCoordinateSaved,
    canSaveSelectedCoordinate,
    updateSelectedCoordinate,
    useCurrentRobotPosition,
    saveSelectedCoordinate,
    changePointLayout,
    resetPointPositions,
    isLoadingCalibration,
    calibrationLoadError,
    isApplyingCalibration,
    isDeletingCalibration,
  } = calibration
  const editingDisabled = isLoadingCalibration
    || Boolean(calibrationLoadError)
    || isApplyingCalibration
    || isDeletingCalibration

  return (
    <aside
      className={`flex min-h-0 w-full flex-col overflow-hidden border-t lg:h-[var(--calibration-video-height)] lg:w-auto lg:border-l lg:border-t-0 ${editingDisabled ? "pointer-events-none opacity-60" : ""}`}
      style={
        {
          "--calibration-video-height": panelHeight
            ? `${panelHeight}px`
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
              <SelectTrigger className="w-full" size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper">
                {POINT_LAYOUT_OPTIONS.map((option) => (
                  <SelectItem key={option.size} value={String(option.size)}>
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
                  variant={selectedPointId === point.id ? "default" : "outline"}
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
                  <p className="text-sm font-medium">{selectedPoint.label}</p>
                </div>
                {videoSize && (
                  <Badge variant="outline" className="text-[10px] font-normal">
                    {Math.round(selectedPoint.x * Math.max(0, videoSize.width - 1))} · {" "}
                    {Math.round(selectedPoint.y * Math.max(0, videoSize.height - 1))}
                  </Badge>
                )}
              </div>

              <div className="flex flex-col gap-3 p-3">
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium">
                      Robot tham chiếu
                    </label>
                    <Badge
                      variant={robotsConnected ? "secondary" : "outline"}
                      className="gap-1.5 text-[10px]"
                    >
                      <span
                        className={`size-1.5 rounded-full ${robotsConnected ? "bg-emerald-500" : "bg-amber-500"}`}
                      />
                      {robotsConnected
                        ? "Realtime"
                        : robotSnapshot
                          ? "Snapshot"
                          : "Đang tải"}
                    </Badge>
                  </div>
                  <Select
                    value={selectedCoordinate.robotId}
                    onValueChange={(robotId) =>
                      updateSelectedCoordinate({
                        robotId,
                        x: "",
                        y: "",
                        source: null,
                      })
                    }
                    disabled={robots.length === 0}
                  >
                    <SelectTrigger className="w-full" size="sm">
                      <SelectValue placeholder="Chưa có robot" />
                    </SelectTrigger>
                    <SelectContent position="popper">
                      {robots.map((robot) => (
                        <SelectItem
                          key={robot.robot_id}
                          value={String(robot.robot_id)}
                        >
                          <span className="flex items-center gap-2">
                            <span
                              className={`size-2 rounded-full ${robot.online ? "bg-emerald-500" : "bg-zinc-400"}`}
                            />
                            Robot #{robot.robot_id}
                            {!robot.online && " · Offline"}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-md border bg-muted/30 px-3 py-2">
                    <p className="text-[11px] text-muted-foreground">
                      Tọa độ X (m)
                    </p>
                    <p className="text-sm">
                      {selectedCoordinate.x || "—"}
                    </p>
                  </div>
                  <div className="rounded-md border bg-muted/30 px-3 py-2">
                    <p className="text-[11px] text-muted-foreground">
                      Tọa độ Y (m)
                    </p>
                    <p className="text-sm">
                      {selectedCoordinate.y || "—"}
                    </p>
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
                      : selectedRobot
                        ? "Robot đang offline"
                        : "Chưa có robot"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={
                      !canSaveSelectedCoordinate || isSelectedCoordinateSaved
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
                    ? `Đã lấy pose từ Robot #${selectedRobot?.robot_id}.`
                    : !selectedRobot
                      ? "Chưa nhận được heartbeat từ robot."
                      : selectedRobot.online
                        ? `Pose mới nhất: X ${selectedRobot.x.toFixed(2)} · Y ${selectedRobot.y.toFixed(2)} m · ${selectedRobot.heartbeat_age_seconds.toFixed(1)}s trước`
                        : `Heartbeat đã cũ ${selectedRobot.heartbeat_age_seconds.toFixed(1)}s; không nên dùng pose này.`}
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
                    Chọn một điểm trên stream hoặc trong danh sách để lấy tọa
                    độ từ robot.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="border-t bg-muted/30 p-4">
        <Button
          size="sm"
          variant="destructive"
          className="w-full"
          onClick={resetPointPositions}
        >
          <RotateCcw />
          Đặt lại vị trí các điểm
        </Button>
      </div>
    </aside>
  )
}
