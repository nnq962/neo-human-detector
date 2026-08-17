import {
  Calculator,
  CheckCircle2,
  Crosshair,
  Eye,
  Monitor,
  Ruler,
  Save,
  Trash2,
  TriangleAlert,
} from "lucide-react"

import type { Camera } from "@/api/cameras.api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import {
  formatCalibrationTime,
  type CameraCalibrationController,
} from "@/hooks/use-camera-calibration"

interface CalibrationSummaryCardProps {
  camera: Camera
  calibration: CameraCalibrationController
}

export function CalibrationSummaryCard({
  camera,
  calibration,
}: CalibrationSummaryCardProps) {
  const {
    points,
    videoSize,
    savedPointCount,
    canCalculateHomography,
    calibrationPreview,
    appliedCalibration,
    calibrationQuality,
    hasResolutionMismatch,
    hasUnappliedChanges,
    calibrationStatusLabel,
    calibrationStatusClassName,
    calibrationStatusDotClassName,
    isCalculatingHomography,
    isApplyingCalibration,
    isDeletingCalibration,
    isLoadingCalibration,
    calibrationLoadError,
    isApplyWarningOpen,
    setIsApplyWarningOpen,
    isDeleteCalibrationOpen,
    setIsDeleteCalibrationOpen,
    previewHomographyCalculation,
    applyCalibration,
    requestApplyCalibration,
    deleteSavedCalibration,
  } = calibration
  const actionsDisabled = isLoadingCalibration || Boolean(calibrationLoadError)

  return (
    <Card className="gap-0 overflow-hidden py-0">
      <CardHeader className="py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle>{camera.name}</CardTitle>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={camera.enabled ? "default" : "secondary"}>
              {camera.enabled ? "Enabled" : "Disabled"}
            </Badge>
            <Badge variant="outline" className={calibrationStatusClassName}>
              {calibrationStatusLabel}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="border-t p-4">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric
              icon={<Crosshair className="size-4" />}
              color="blue"
              label="Điểm đã lưu"
              value={`${savedPointCount} / ${points.length}`}
              hint="Tối thiểu 4 điểm"
            />
            <Metric
              icon={<CheckCircle2 className="size-4" />}
              color="emerald"
              label="Điểm hợp lệ"
              value={
                calibrationPreview
                  ? `${calibrationPreview.quality.valid_points} / ${calibrationPreview.quality.total_points}`
                  : "—"
              }
              hint="Tốt khi đạt từ 90%"
            />
            <Metric
              icon={<Ruler className="size-4" />}
              color="amber"
              label="Sai số kiểm tra"
              value={
                calibrationPreview?.quality.validation_rmse_m != null
                  ? `${calibrationPreview.quality.validation_rmse_m.toFixed(2)} m`
                  : "—"
              }
              hint={
                calibrationPreview?.quality.validation_rmse_m != null
                  ? "≤ 0.10 m là tốt"
                  : calibrationPreview &&
                      calibrationPreview.quality.total_points > 4
                    ? "Hãy tính lại để đánh giá"
                    : "Cần nhiều hơn 4 điểm"
              }
            />
            <Metric
              icon={<Monitor className="size-4" />}
              color="violet"
              label="Độ phân giải"
              value={videoSize ? `${videoSize.width} × ${videoSize.height}` : "—"}
              hint="Theo video gốc"
            />
          </div>

          <div className="space-y-3 border-t pt-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm">
                <span
                  className={`size-2 shrink-0 rounded-full ${calibrationStatusDotClassName}`}
                />
                <span className="font-medium">
                  {appliedCalibration && hasUnappliedChanges
                    ? "Các point đã thay đổi, cần tính và áp dụng lại"
                    : appliedCalibration
                      ? `Đã áp dụng lúc ${formatCalibrationTime(appliedCalibration.updated_at)}`
                      : calibrationPreview
                        ? calibrationQuality?.label
                        : canCalculateHomography
                          ? "Đã đủ dữ liệu để tính ma trận H"
                          : `Cần thêm ${4 - savedPointCount} điểm đã lưu`}
                </span>
              </div>
              {hasResolutionMismatch && appliedCalibration && videoSize && (
                <div className="mt-1.5 flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                  Calibration dùng {appliedCalibration.image_size.width} ×{" "}
                  {appliedCalibration.image_size.height}, video hiện tại là{" "}
                  {videoSize.width} × {videoSize.height}.
                </div>
              )}
            </div>

            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {calibrationPreview && (
                <CalibrationDetailsDialog calibration={calibration} />
              )}
              {appliedCalibration && (
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  className="w-full"
                  disabled={actionsDisabled}
                  onClick={() => setIsDeleteCalibrationOpen(true)}
                >
                  <Trash2 />
                  Xóa calibration đã lưu
                </Button>
              )}
              <Button
                type="button"
                size="sm"
                className="w-full"
                variant={calibrationPreview ? "outline" : "default"}
                disabled={
                  !canCalculateHomography ||
                  !videoSize ||
                  actionsDisabled ||
                  isCalculatingHomography
                }
                onClick={previewHomographyCalculation}
              >
                {isCalculatingHomography ? <Spinner /> : <Calculator />}
                {isCalculatingHomography
                  ? "Đang tính H..."
                  : calibrationPreview
                    ? "Tính lại H"
                    : "Tính và kiểm tra H"}
              </Button>
              <Button
                type="button"
                size="sm"
                className="w-full"
                disabled={
                  !calibrationPreview ||
                  actionsDisabled ||
                  calibrationPreview.quality.rating === "RECALIBRATE" ||
                  isApplyingCalibration ||
                  isCalculatingHomography
                }
                onClick={requestApplyCalibration}
              >
                {isApplyingCalibration ? <Spinner /> : <Save />}
                {isApplyingCalibration
                  ? "Đang áp dụng..."
                  : appliedCalibration
                    ? "Áp dụng lại"
                    : "Áp dụng calibration"}
              </Button>
            </div>
          </div>
        </div>

        <Dialog
          open={isApplyWarningOpen}
          onOpenChange={(open) => {
            if (!isApplyingCalibration) setIsApplyWarningOpen(open)
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Xác nhận áp dụng calibration</DialogTitle>
              <DialogDescription>
                {calibrationPreview?.quality.rating === "LIMITED"
                  ? "Bốn điểm đủ để tính H nhưng chưa có dữ liệu dư để đánh giá độ ổn định."
                  : "Kết quả còn point bị loại hoặc sai số cần được kiểm tra."}
              </DialogDescription>
            </DialogHeader>
            {calibrationPreview && (
              <div className="rounded-lg border bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
                {calibrationPreview.quality.valid_points} /{" "}
                {calibrationPreview.quality.total_points} điểm hợp lệ
                {calibrationPreview.quality.validation_rmse_m != null
                  ? ` · sai số kiểm tra ${calibrationPreview.quality.validation_rmse_m.toFixed(3)} m`
                  : " · chưa thể đánh giá sai số với 4 điểm"}
              </div>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={isApplyingCalibration}
                onClick={() => setIsApplyWarningOpen(false)}
              >
                Kiểm tra lại
              </Button>
              <Button
                type="button"
                disabled={isApplyingCalibration}
                onClick={() => void applyCalibration(true)}
              >
                {isApplyingCalibration ? <Spinner /> : <Save />}
                Vẫn áp dụng
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog
          open={isDeleteCalibrationOpen}
          onOpenChange={(open) => {
            if (!isDeletingCalibration) setIsDeleteCalibrationOpen(open)
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Xóa calibration đã lưu?</DialogTitle>
              <DialogDescription>
                Ma trận H sẽ bị xóa khỏi cấu hình camera. Stream, zones và các
                point đang hiển thị trên trang không bị xóa.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={isDeletingCalibration}
                onClick={() => setIsDeleteCalibrationOpen(false)}
              >
                Giữ lại
              </Button>
              <Button
                type="button"
                variant="destructive"
                disabled={isDeletingCalibration}
                onClick={() => void deleteSavedCalibration()}
              >
                {isDeletingCalibration ? <Spinner /> : <Trash2 />}
                Xóa calibration
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  )
}

const METRIC_COLORS = {
  blue: {
    card: "from-blue-500/[0.08]",
    icon: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  },
  emerald: {
    card: "from-emerald-500/[0.08]",
    icon: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  amber: {
    card: "from-amber-500/[0.08]",
    icon: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  violet: {
    card: "from-violet-500/[0.08]",
    icon: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  },
} as const

interface MetricProps {
  icon: React.ReactNode
  color: keyof typeof METRIC_COLORS
  label: string
  value: string
  hint: string
}

function Metric({ icon, color, label, value, hint }: MetricProps) {
  const colors = METRIC_COLORS[color]

  return (
    <div
      className={`rounded-xl border bg-gradient-to-br ${colors.card} to-transparent p-3.5`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`grid size-9 shrink-0 place-items-center rounded-lg ${colors.icon}`}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-0.5 text-xl font-semibold">{value}</p>
          <p className="mt-1 text-[10px] text-muted-foreground">{hint}</p>
        </div>
      </div>
    </div>
  )
}

function CalibrationDetailsDialog({
  calibration,
}: {
  calibration: CameraCalibrationController
}) {
  const { calibrationPreview, calibrationQuality, points } = calibration
  if (!calibrationPreview) return null

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="w-full">
          <Eye />
          Xem ma trận và cách đánh giá
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)] overflow-hidden sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Chi tiết ma trận H</DialogTitle>
          <DialogDescription>
            Kết quả RANSAC cho phép ánh xạ pixel sang tọa độ robot.
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="min-h-0">
          <div className="space-y-4 pr-3">
          <div className="grid grid-cols-3 overflow-hidden rounded-lg border">
            {calibrationPreview.homography.flatMap((row, rowIndex) =>
              row.map((value, columnIndex) => (
                <div
                  key={`${rowIndex}-${columnIndex}`}
                  className={`p-2 text-center text-xs tabular-nums sm:p-3 sm:text-sm ${
                    columnIndex < 2 ? "border-r" : ""
                  } ${rowIndex < 2 ? "border-b" : ""}`}
                >
                  {value.toFixed(5)}
                </div>
              )),
            )}
          </div>
          <div
            className={`flex items-center gap-2 rounded-lg p-3 text-sm ${calibrationQuality?.className ?? ""}`}
          >
            <CheckCircle2 className="size-4 shrink-0" />
            <span>
              <span className="font-medium">{calibrationQuality?.label}:</span>{" "}
              {calibrationPreview.quality.valid_points} /{" "}
              {calibrationPreview.quality.total_points} điểm hợp lệ
              {calibrationPreview.quality.validation_rmse_m != null
                ? ` · sai số kiểm tra ${calibrationPreview.quality.validation_rmse_m.toFixed(2)} m`
                : " · chưa đủ dữ liệu để đánh giá sai số"}
            </span>
          </div>

          <p className="text-xs text-muted-foreground">
            Sai số khớp trên các điểm hợp lệ:{" "}
            {calibrationPreview.quality.rmse_inlier_m.toFixed(3)} m. Sai số này
            chỉ dùng để kiểm tra kỹ thuật, không phải sai số dự đoán.
          </p>

          <div className="overflow-hidden rounded-lg border">
            <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-2">
              <p className="text-sm font-medium">Sai số kiểm tra từng điểm</p>
              <p className="text-[11px] text-muted-foreground">Theo mét</p>
            </div>
            <div className="max-h-44 divide-y overflow-y-auto">
              {calibrationPreview.points.map((result) => (
                <div
                  key={result.id}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-xs"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className={`size-2 shrink-0 rounded-full ${result.valid ? "bg-emerald-500" : "bg-red-500"}`}
                    />
                    <span className="truncate font-medium">
                      {points.find((point) => point.id === result.id)?.label ??
                        result.id}
                    </span>
                    <span className="text-muted-foreground">
                      {result.valid ? "Hợp lệ" : "Bị loại"}
                    </span>
                  </div>
                  <span className="shrink-0 tabular-nums">
                    {result.validation_error_m != null
                      ? `${result.validation_error_m.toFixed(3)} m`
                      : "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-3 rounded-lg border p-3">
            <QualityGuide />
          </div>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

function QualityGuide() {
  return (
    <>
      <div>
        <p className="text-sm font-medium">Cách đánh giá điểm hợp lệ</p>
        <div className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          <span className="text-emerald-600">Từ 90%</span>
          <span className="text-muted-foreground">Tốt</span>
          <span className="text-amber-600">75–89%</span>
          <span className="text-muted-foreground">
            Cần kiểm tra các điểm bị loại
          </span>
          <span className="text-red-600">Dưới 75%</span>
          <span className="text-muted-foreground">Nên đo lại calibration</span>
        </div>
      </div>

      <div className="border-t pt-3">
        <p className="text-sm font-medium">Cách đánh giá sai số kiểm tra</p>
        <div className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          <span className="text-emerald-600">≤ 0.05 m</span>
          <span className="text-muted-foreground">Rất tốt</span>
          <span className="text-emerald-600">0.05–0.10 m</span>
          <span className="text-muted-foreground">Tốt</span>
          <span className="text-amber-600">0.10–0.20 m</span>
          <span className="text-muted-foreground">Cần kiểm tra</span>
          <span className="text-red-600">&gt; 0.20 m</span>
          <span className="text-muted-foreground">Nên calibration lại</span>
        </div>
      </div>
    </>
  )
}
