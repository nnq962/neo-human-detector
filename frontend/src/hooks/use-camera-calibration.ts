import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import {
  cameraCalibrationApi,
  type CalibrationPreviewRequest,
  type CalibrationPreviewResult,
  type CameraCalibration,
} from "@/api/camera-calibration.api"
import { useRobotHeartbeats } from "@/hooks/use-robot-heartbeats"
import {
  createCalibrationPointPositions,
  type CalibrationPointPosition,
} from "@/lib/calibration-points"

export const POINT_LAYOUT_OPTIONS = [
  { size: 2, label: "2×2 · 4 điểm — Thiết lập nhanh" },
  { size: 3, label: "3×3 · 9 điểm — Khuyến nghị" },
  { size: 4, label: "4×4 · 16 điểm — Độ phủ cao" },
]

export interface RobotCoordinateValue {
  robotId: string
  x: string
  y: string
  source: "robot" | null
}

const EMPTY_ROBOT_COORDINATE: RobotCoordinateValue = {
  robotId: "",
  x: "",
  y: "",
  source: null,
}

function getCalibrationQuality(result: CalibrationPreviewResult) {
  switch (result.quality.rating) {
    case "GOOD":
      return {
        label: "Kết quả tốt",
        className:
          "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
        dotClassName: "bg-emerald-500",
      }
    case "LIMITED":
      return {
        label: "Cần thêm điểm để đánh giá",
        className: "bg-blue-500/10 text-blue-700 dark:text-blue-400",
        dotClassName: "bg-blue-500",
      }
    case "CHECK":
      return {
        label: "Cần kiểm tra",
        className: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
        dotClassName: "bg-amber-500",
      }
    case "RECALIBRATE":
      return {
        label: "Nên đo lại",
        className: "bg-red-500/10 text-red-700 dark:text-red-400",
        dotClassName: "bg-red-500",
      }
  }
}

function savedCalibrationToPreview(
  calibration: CameraCalibration,
): CalibrationPreviewResult {
  return {
    camera_id: calibration.camera_id,
    image_size: calibration.image_size,
    direction: calibration.direction,
    method: calibration.method,
    ransac_threshold_m: calibration.ransac_threshold_m,
    homography: calibration.homography,
    quality: calibration.quality,
    points: calibration.points.map((point) => ({
      id: point.id,
      valid: point.valid,
      predicted_world: {
        x: point.predicted_world[0],
        y: point.predicted_world[1],
      },
      error_m: point.error_m,
      validation_error_m: point.validation_error_m ?? null,
    })),
  }
}

export function formatCalibrationTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString("vi-VN", { hour12: false })
}

export function useCameraCalibration(cameraId: string, enabled: boolean) {
  const { snapshot: robotSnapshot, connected: robotsConnected } =
    useRobotHeartbeats()
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
  const [calibrationPreview, setCalibrationPreview] =
    useState<CalibrationPreviewResult | null>(null)
  const [appliedCalibration, setAppliedCalibration] =
    useState<CameraCalibration | null>(null)
  const [isCalculatingHomography, setIsCalculatingHomography] = useState(false)
  const [isLoadingCalibration, setIsLoadingCalibration] = useState(true)
  const [isApplyingCalibration, setIsApplyingCalibration] = useState(false)
  const [isDeletingCalibration, setIsDeletingCalibration] = useState(false)
  const [hasUnappliedChanges, setHasUnappliedChanges] = useState(false)
  const [isApplyWarningOpen, setIsApplyWarningOpen] = useState(false)
  const [isDeleteCalibrationOpen, setIsDeleteCalibrationOpen] = useState(false)
  const calibrationRevisionRef = useRef(0)

  useEffect(() => {
    if (!enabled) return

    let cancelled = false
    queueMicrotask(() => {
      if (!cancelled) setIsLoadingCalibration(true)
    })

    cameraCalibrationApi.get(cameraId)
      .then((calibration) => {
        if (cancelled) return

        if (!calibration) {
          setPointLayoutSize(2)
          setPoints(createCalibrationPointPositions(2))
          setRobotCoordinates({})
          setSavedRobotCoordinates({})
          setCalibrationPreview(null)
          setAppliedCalibration(null)
          setHasUnappliedChanges(false)
          return
        }

        const restoredPoints = calibration.points.map((point, index) => ({
          id: point.id,
          label: `P${index + 1}`,
          x: point.pixel[0] / calibration.image_size.width,
          y: point.pixel[1] / calibration.image_size.height,
        }))
        const restoredCoordinates = Object.fromEntries(
          calibration.points.map((point) => [
            point.id,
            {
              robotId: point.robot_id === null ? "" : String(point.robot_id),
              x: String(point.world[0]),
              y: String(point.world[1]),
              source: point.robot_id === null ? null : "robot" as const,
            },
          ]),
        )
        const restoredLayoutSize = Math.sqrt(restoredPoints.length)

        if ([2, 3, 4].includes(restoredLayoutSize)) {
          setPointLayoutSize(restoredLayoutSize)
        }
        setPoints(restoredPoints)
        setRobotCoordinates(restoredCoordinates)
        setSavedRobotCoordinates(restoredCoordinates)
        setCalibrationPreview(savedCalibrationToPreview(calibration))
        setAppliedCalibration(calibration)
        setHasUnappliedChanges(false)
      })
      .catch((error) => {
        if (cancelled) return
        toast.error(
          error instanceof Error
            ? error.message
            : "Không thể tải calibration đã lưu.",
        )
      })
      .finally(() => {
        if (!cancelled) setIsLoadingCalibration(false)
      })

    return () => {
      cancelled = true
    }
  }, [cameraId, enabled])

  const selectedPoint =
    points.find((point) => point.id === selectedPointId) ?? null
  const robots = robotSnapshot?.robots ?? []
  const defaultRobotId = String(
    robots.find((robot) => robot.online)?.robot_id ??
      robots[0]?.robot_id ??
      "",
  )
  const defaultRobotCoordinate: RobotCoordinateValue = {
    ...EMPTY_ROBOT_COORDINATE,
    robotId: defaultRobotId,
  }
  const selectedCoordinate = selectedPoint
    ? (robotCoordinates[selectedPoint.id] ?? defaultRobotCoordinate)
    : null
  const selectedRobot = robots.find(
    (robot) => String(robot.robot_id) === selectedCoordinate?.robotId,
  )
  const savedSelectedCoordinate = selectedPoint
    ? savedRobotCoordinates[selectedPoint.id]
    : undefined
  const isSelectedCoordinateSaved = Boolean(
    selectedCoordinate &&
      savedSelectedCoordinate &&
      selectedCoordinate.source === "robot" &&
      savedSelectedCoordinate.source === "robot" &&
      selectedCoordinate.robotId === savedSelectedCoordinate.robotId &&
      selectedCoordinate.x === savedSelectedCoordinate.x &&
      selectedCoordinate.y === savedSelectedCoordinate.y,
  )
  const canSaveSelectedCoordinate = Boolean(
    selectedCoordinate?.robotId &&
      selectedCoordinate.source === "robot" &&
      selectedCoordinate.x.trim() &&
      selectedCoordinate.y.trim() &&
      Number.isFinite(Number(selectedCoordinate.x)) &&
      Number.isFinite(Number(selectedCoordinate.y)),
  )
  const savedPointCount = points.filter(
    (point) => savedRobotCoordinates[point.id]?.source === "robot",
  ).length
  const canCalculateHomography = savedPointCount >= 4
  const calibrationQuality = calibrationPreview
    ? getCalibrationQuality(calibrationPreview)
    : null
  const hasResolutionMismatch = Boolean(
    appliedCalibration &&
      videoSize &&
      (appliedCalibration.image_size.width !== videoSize.width ||
        appliedCalibration.image_size.height !== videoSize.height),
  )
  const calibrationStatusLabel = isLoadingCalibration
    ? "Đang tải calibration"
    : appliedCalibration && hasUnappliedChanges
      ? "Có thay đổi chưa áp dụng"
      : appliedCalibration
        ? "Đã áp dụng"
        : calibrationPreview
          ? "Đã tính H"
          : canCalculateHomography
            ? "Sẵn sàng tính"
            : "Chưa đủ điểm"
  const calibrationStatusClassName = isLoadingCalibration
    ? undefined
    : appliedCalibration && hasUnappliedChanges
      ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400"
      : appliedCalibration
        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
        : calibrationPreview
          ? calibrationQuality?.className
          : canCalculateHomography
            ? "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400"
            : undefined
  const calibrationStatusDotClassName = appliedCalibration && hasUnappliedChanges
    ? "bg-amber-500"
    : appliedCalibration
      ? "bg-emerald-500"
      : calibrationPreview
        ? calibrationQuality?.dotClassName
        : canCalculateHomography
          ? "bg-blue-500"
          : "bg-amber-500"

  function invalidateCalibrationPreview() {
    calibrationRevisionRef.current += 1
    setCalibrationPreview(null)
    setIsCalculatingHomography(false)
    if (appliedCalibration) setHasUnappliedChanges(true)
  }

  function updateSelectedCoordinate(updates: Partial<RobotCoordinateValue>) {
    if (!selectedPoint) return
    setRobotCoordinates((current) => ({
      ...current,
      [selectedPoint.id]: {
        ...(current[selectedPoint.id] ?? defaultRobotCoordinate),
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
      toast.error("Vui lòng lấy tọa độ hiện tại từ robot.")
      return
    }
    setSavedRobotCoordinates((current) => ({
      ...current,
      [selectedPoint.id]: { ...selectedCoordinate },
    }))
    invalidateCalibrationPreview()
    toast.success(`Đã lưu tạm tọa độ cho ${selectedPoint.label}.`)
  }

  function buildCalibrationRequest(): CalibrationPreviewRequest | null {
    if (!videoSize) return null

    return {
      image_size: videoSize,
      points: points.flatMap((point) => {
        const coordinate = savedRobotCoordinates[point.id]
        if (!coordinate || coordinate.source !== "robot") return []

        const robotId = Number(coordinate.robotId)
        return [{
          id: point.id,
          pixel: {
            u: Math.round(point.x * videoSize.width),
            v: Math.round(point.y * videoSize.height),
          },
          world: {
            x: Number(coordinate.x),
            y: Number(coordinate.y),
          },
          robot_id: Number.isInteger(robotId) ? robotId : null,
        }]
      }),
    }
  }

  async function previewHomographyCalculation() {
    if (!canCalculateHomography) {
      toast.error("Cần lưu ít nhất 4 điểm để tính ma trận H.")
      return
    }
    if (!videoSize) {
      toast.error("Chưa nhận được độ phân giải video gốc.")
      return
    }

    const revision = calibrationRevisionRef.current
    const request = buildCalibrationRequest()
    if (!request) return

    setIsCalculatingHomography(true)
    try {
      const result = await cameraCalibrationApi.preview(cameraId, request)
      if (revision !== calibrationRevisionRef.current) return
      setCalibrationPreview(result)
      toast.success("Đã tính và kiểm tra ma trận H.")
    } catch (error) {
      if (revision !== calibrationRevisionRef.current) return
      setCalibrationPreview(null)
      toast.error(
        error instanceof Error ? error.message : "Không thể tính ma trận H.",
      )
    } finally {
      if (revision === calibrationRevisionRef.current) {
        setIsCalculatingHomography(false)
      }
    }
  }

  async function applyCalibration(acceptWarning: boolean) {
    const request = buildCalibrationRequest()
    if (!request || !calibrationPreview) return

    setIsApplyingCalibration(true)
    try {
      const calibration = await cameraCalibrationApi.apply(cameraId, {
        ...request,
        ransac_threshold_m: calibrationPreview.ransac_threshold_m,
        accept_warning: acceptWarning,
      })
      setAppliedCalibration(calibration)
      setCalibrationPreview(savedCalibrationToPreview(calibration))
      setHasUnappliedChanges(false)
      setIsApplyWarningOpen(false)
      toast.success("Đã áp dụng calibration vào cấu hình camera.")
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Không thể áp dụng calibration.",
      )
    } finally {
      setIsApplyingCalibration(false)
    }
  }

  function requestApplyCalibration() {
    if (!calibrationPreview) return
    if (calibrationPreview.quality.rating === "RECALIBRATE") {
      toast.error("Chất lượng quá thấp; vui lòng đo lại calibration.")
      return
    }
    if (["CHECK", "LIMITED"].includes(calibrationPreview.quality.rating)) {
      setIsApplyWarningOpen(true)
      return
    }
    void applyCalibration(false)
  }

  async function deleteSavedCalibration() {
    setIsDeletingCalibration(true)
    try {
      await cameraCalibrationApi.delete(cameraId)
      setAppliedCalibration(null)
      setHasUnappliedChanges(false)
      setIsDeleteCalibrationOpen(false)
      toast.success("Đã xóa calibration khỏi cấu hình camera.")
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Không thể xóa calibration.",
      )
    } finally {
      setIsDeletingCalibration(false)
    }
  }

  function updatePointPositions(nextPoints: CalibrationPointPosition[]) {
    setPoints(nextPoints)
    invalidateCalibrationPreview()
  }

  function changePointLayout(value: string) {
    const size = Number(value)
    setPointLayoutSize(size)
    setPoints(createCalibrationPointPositions(size))
    setRobotCoordinates({})
    setSavedRobotCoordinates({})
    invalidateCalibrationPreview()
    setSelectedPointId(null)
  }

  function resetPointPositions() {
    setPoints(createCalibrationPointPositions(pointLayoutSize))
    invalidateCalibrationPreview()
    setSelectedPointId(null)
  }

  return {
    pointLayoutSize,
    points,
    selectedPointId,
    setSelectedPointId,
    videoSize,
    setVideoSize,
    selectedPoint,
    selectedCoordinate,
    selectedRobot,
    robots,
    robotSnapshot,
    robotsConnected,
    isSelectedCoordinateSaved,
    canSaveSelectedCoordinate,
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
    isApplyWarningOpen,
    setIsApplyWarningOpen,
    isDeleteCalibrationOpen,
    setIsDeleteCalibrationOpen,
    updateSelectedCoordinate,
    useCurrentRobotPosition,
    saveSelectedCoordinate,
    previewHomographyCalculation,
    applyCalibration,
    requestApplyCalibration,
    deleteSavedCalibration,
    updatePointPositions,
    changePointLayout,
    resetPointPositions,
  }
}

export type CameraCalibrationController = ReturnType<typeof useCameraCalibration>
