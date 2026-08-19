import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type PointerEvent,
} from "react"
import { MapPin } from "lucide-react"

import type { RobotTask } from "@/api/robot-tasks.api"
import { CameraPreview } from "@/components/camera-preview"
import type { VideoSize } from "@/components/camera-preview/types"
import { NavigationTaskMarker } from "@/components/navigation/navigation-task-marker"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuGroup,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu"
import { useNavigationTaskActions } from "@/hooks/use-navigation-task-actions"
import type { Camera } from "@/hooks/use-cameras"
import {
  mapRuntimeTaskToNavigation,
  TASK_COMPLETION_FADE_DELAY_MS,
  TASK_COMPLETION_REMOVE_DELAY_MS,
} from "@/lib/navigation-tasks"
import {
  clientPointToNavigationPoint,
  type NavigationPoint,
} from "@/lib/navigation-drafts"

interface NavigationCameraCellProps {
  camera: Camera
  runtimeTasks: RobotTask[]
  showBboxes: boolean
  showZones: boolean
}

export const NavigationCameraCell = memo(function NavigationCameraCell({
  camera,
  runtimeTasks,
  showBboxes,
  showZones,
}: NavigationCameraCellProps) {
  const previewRef = useRef<HTMLDivElement>(null)
  const pendingTaskPopoverIdRef = useRef<string | null>(null)
  const [contextPoint, setContextPoint] = useState<NavigationPoint | null>(null)
  const [openTaskId, setOpenTaskId] = useState<string | null>(null)
  const [videoSize, setVideoSize] = useState<VideoSize | null>(null)
  const [taskExpiryVersion, setTaskExpiryVersion] = useState(0)
  const taskActions = useNavigationTaskActions({
    cameraId: camera.id,
    cameraName: camera.name,
    runtimeTasks,
  })

  useEffect(() => {
    const now = Date.now()
    let nextDeadline = Number.POSITIVE_INFINITY

    runtimeTasks.forEach((task) => {
      if (task.status !== "COMPLETED" || !task.completed_at) return
      const completedAt = new Date(task.completed_at).getTime()
      if (!Number.isFinite(completedAt)) return

      const deadlines = [
        completedAt + TASK_COMPLETION_FADE_DELAY_MS,
        completedAt + TASK_COMPLETION_REMOVE_DELAY_MS,
      ]
      deadlines.forEach((deadline) => {
        if (deadline > now && deadline < nextDeadline) {
          nextDeadline = deadline
        }
      })
    })

    if (!Number.isFinite(nextDeadline)) return
    const timer = window.setTimeout(() => {
      setTaskExpiryVersion((current) => current + 1)
    }, Math.max(0, nextDeadline - now + 16))
    return () => window.clearTimeout(timer)
  }, [runtimeTasks, taskExpiryVersion])

  const runtimeClock = Date.now()

  const systemTasks = useMemo(() => runtimeTasks.flatMap((task) => {
    const mapped = mapRuntimeTaskToNavigation(
      task,
      camera,
      videoSize,
      runtimeClock,
    )
    return mapped ? [mapped] : []
  }), [camera, runtimeClock, runtimeTasks, videoSize])
  const tasks = [...taskActions.drafts, ...systemTasks]

  function updateContextPoint(clientX: number, clientY: number) {
    const bounds = previewRef.current?.getBoundingClientRect()
    if (!bounds) return
    setContextPoint(clientPointToNavigationPoint(clientX, clientY, bounds))
  }

  function handleContextMenu(event: MouseEvent<HTMLDivElement>) {
    updateContextPoint(event.clientX, event.clientY)
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (
      event.pointerType !== "touch"
      && event.pointerType !== "pen"
      && event.button !== 2
    ) {
      return
    }
    updateContextPoint(event.clientX, event.clientY)
  }

  function createTask() {
    if (!contextPoint) return
    const task = taskActions.createDraft(contextPoint, "low", videoSize)
    pendingTaskPopoverIdRef.current = task.id
  }

  function handleContextMenuOpenChangeComplete(open: boolean) {
    if (open || !pendingTaskPopoverIdRef.current) return
    const taskId = pendingTaskPopoverIdRef.current
    pendingTaskPopoverIdRef.current = null
    setOpenTaskId(taskId)
  }

  return (
    <ContextMenu onOpenChangeComplete={handleContextMenuOpenChangeComplete}>
      <ContextMenuTrigger className="block w-full">
        <div
          ref={previewRef}
          className="relative aspect-video overflow-hidden rounded-lg ring-1 ring-border"
          onContextMenu={handleContextMenu}
          onPointerDownCapture={handlePointerDown}
        >
          <CameraPreview
            src={camera.webrtc_address ?? ""}
            cameraId={camera.id}
            zones={showZones ? camera.zones : []}
            bboxCameraId={showBboxes ? camera.id : null}
            hideFaceKeypoints={true}
            onVideoSizeChange={setVideoSize}
          />
          <div className="pointer-events-none absolute bottom-3 left-3 z-30 rounded-md bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
            {camera.name}
          </div>

          {tasks.map((task) => (
            <NavigationTaskMarker
              key={task.id}
              task={task}
              cameraName={camera.name}
              open={openTaskId === task.id}
              submitting={taskActions.submittingDraftIds.has(task.id)}
              canceling={taskActions.cancelingTaskIds.has(task.id)}
              onOpenChange={(open) => setOpenTaskId((currentTaskId) => {
                if (open) return task.id
                return currentTaskId === task.id ? null : currentTaskId
              })}
              onPriorityChange={(priority) => {
                if (task.kind === "draft") {
                  taskActions.changeDraftPriority(task.id, priority)
                }
              }}
              onCancel={() => {
                if (task.kind === "draft") {
                  taskActions.removeDraft(task)
                  setOpenTaskId(null)
                  return
                }
                void taskActions.cancelRuntimeTask(task)
              }}
              onSubmit={() => {
                if (task.kind !== "draft") return
                void taskActions.submitDraft(task).then((submitted) => {
                  if (submitted) setOpenTaskId(null)
                })
              }}
            />
          ))}
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuGroup>
          <ContextMenuLabel>Điều khiển {camera.name}</ContextMenuLabel>
        </ContextMenuGroup>
        <ContextMenuSeparator />
        <ContextMenuGroup>
          <ContextMenuItem onClick={createTask}>
            <MapPin />
            Tạo task
          </ContextMenuItem>
        </ContextMenuGroup>
      </ContextMenuContent>
    </ContextMenu>
  )
})
