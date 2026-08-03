import { useEffect, useMemo, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Bot } from "lucide-react"
import { cameraCalibrationApi } from "@/api/camera-calibration.api"
import { useRobotHeartbeats } from "@/hooks/use-robot-heartbeats"
import { computeLayout } from "./layout"
import {
  invertMatrix3x3,
  projectPoint,
  toMatrix3x3,
} from "./homography"
import type { PreviewSize, VideoSize } from "./types"

const RELOCATION_FADE_MS = 180

interface ProjectedRobot {
  id: number
  left: number
  top: number
}

interface RobotOverlayProps {
  cameraId: string | null
  previewSize: PreviewSize
  videoSize: VideoSize
}

function robotPositionsEqual(
  current: ProjectedRobot[],
  next: ProjectedRobot[],
) {
  return current.length === next.length && current.every((robot, index) => {
    const other = next[index]
    return other?.id === robot.id
      && Math.abs(other.left - robot.left) < 0.1
      && Math.abs(other.top - robot.top) < 0.1
  })
}

export function RobotOverlay({
  cameraId,
  previewSize,
  videoSize,
}: RobotOverlayProps) {
  const { snapshot, connected } = useRobotHeartbeats()
  const { data: calibration } = useQuery({
    queryKey: ["camera-calibration", cameraId],
    queryFn: () => cameraCalibrationApi.get(cameraId!),
    enabled: Boolean(cameraId),
    staleTime: 60_000,
  })
  const [displayedRobots, setDisplayedRobots] = useState<ProjectedRobot[]>([])
  const [visible, setVisible] = useState(false)
  const displayedRobotsRef = useRef(displayedRobots)

  useEffect(() => {
    displayedRobotsRef.current = displayedRobots
  }, [displayedRobots])

  const projectedRobots = useMemo(() => {
    if (
      !connected
      || !calibration
      || !videoSize.width
      || !videoSize.height
      || calibration.image_size.width !== videoSize.width
      || calibration.image_size.height !== videoSize.height
    ) return []

    const homography = toMatrix3x3(calibration.homography)
    const worldToPixel = homography ? invertMatrix3x3(homography) : null
    const layout = computeLayout(previewSize, videoSize)
    if (!worldToPixel || !layout) return []

    return (snapshot?.robots ?? [])
      .filter((robot) => robot.online)
      .flatMap((robot): ProjectedRobot[] => {
        const pixel = projectPoint([robot.x, robot.y], worldToPixel)
        if (!pixel) return []
        const [pixelX, pixelY] = pixel
        if (
          pixelX < 0
          || pixelX > calibration.image_size.width
          || pixelY < 0
          || pixelY > calibration.image_size.height
        ) return []

        return [{
          id: robot.robot_id,
          left: layout.offsetX + pixelX * layout.scale,
          top: layout.offsetY + pixelY * layout.scale,
        }]
      })
      .sort((first, second) => first.id - second.id)
  }, [calibration, connected, previewSize, snapshot, videoSize])

  useEffect(() => {
    if (robotPositionsEqual(displayedRobotsRef.current, projectedRobots)) return

    const fadeTimer = setTimeout(() => setVisible(false), 0)
    const relocateTimer = setTimeout(() => {
      setDisplayedRobots(projectedRobots)
      setVisible(projectedRobots.length > 0)
    }, displayedRobotsRef.current.length > 0 ? RELOCATION_FADE_MS : 0)

    return () => {
      clearTimeout(fadeTimer)
      clearTimeout(relocateTimer)
    }
  }, [projectedRobots])

  if (!calibration) return null

  return (
    <div
      className="pointer-events-none absolute inset-0 z-[5] transition-opacity ease-out"
      style={{
        opacity: visible ? 1 : 0,
        transitionDuration: `${RELOCATION_FADE_MS}ms`,
      }}
    >
      {displayedRobots.map((robot) => (
        <div
          key={robot.id}
          className="absolute flex -translate-x-1/2 -translate-y-full flex-col items-center drop-shadow-md"
          style={{ left: robot.left, top: robot.top }}
        >
          <div className="flex h-8 items-center gap-1 rounded-lg border-2 border-white bg-violet-600 px-2 text-[10px] font-bold text-white shadow-sm">
            <Bot className="size-4" strokeWidth={2.5} />
            <span>#{robot.id}</span>
          </div>
          <svg
            aria-hidden="true"
            viewBox="0 0 14 9"
            className="-mt-0.5 h-2.5 w-3.5 overflow-visible"
          >
            <path
              d="M1 1 L7 8 L13 1 Z"
              className="fill-violet-600 stroke-white"
              strokeWidth="2"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      ))}
    </div>
  )
}
