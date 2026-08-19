import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import {
  robotTasksApi,
  type RobotTask,
} from "@/api/robot-tasks.api"
import type { VideoSize } from "@/components/camera-preview/types"
import {
  createNavigationDraft,
  type NavigationPoint,
} from "@/lib/navigation-drafts"
import type {
  NavigationTask,
  NavigationTaskPriority,
} from "@/lib/navigation-tasks"

const CANCEL_ACKNOWLEDGED_STATUSES = new Set<RobotTask["status"]>([
  "CANCELING",
  "CANCELED",
  "COMPLETED",
  "FAILED",
])

interface UseNavigationTaskActionsOptions {
  cameraId: string
  cameraName: string
  runtimeTasks: RobotTask[]
}

export function useNavigationTaskActions({
  cameraId,
  cameraName,
  runtimeTasks,
}: UseNavigationTaskActionsOptions) {
  const [drafts, setDrafts] = useState<NavigationTask[]>([])
  const [submittingDraftIds, setSubmittingDraftIds] = useState<Set<string>>(
    () => new Set(),
  )
  const [submittedTaskUidByDraftId, setSubmittedTaskUidByDraftId] = useState<
    Map<string, string>
  >(() => new Map())
  const [requestedCancelTaskIds, setRequestedCancelTaskIds] = useState<Set<string>>(
    () => new Set(),
  )
  const cancelingTaskIds = useMemo(() => {
    const tasksByUid = new Map(runtimeTasks.map((task) => [task.uid, task]))
    return new Set([...requestedCancelTaskIds].filter((uid) => {
      const task = tasksByUid.get(uid)
      return task !== undefined && !CANCEL_ACKNOWLEDGED_STATUSES.has(task.status)
    }))
  }, [requestedCancelTaskIds, runtimeTasks])
  const runtimeTaskUids = useMemo(
    () => new Set(runtimeTasks.map((task) => task.uid)),
    [runtimeTasks],
  )
  const visibleDrafts = useMemo(() => drafts.filter((draft) => {
    const runtimeTaskUid = submittedTaskUidByDraftId.get(draft.id)
    return runtimeTaskUid === undefined || !runtimeTaskUids.has(runtimeTaskUid)
  }), [drafts, runtimeTaskUids, submittedTaskUidByDraftId])
  const pendingDraftIds = useMemo(() => new Set([
    ...submittingDraftIds,
    ...[...submittedTaskUidByDraftId]
      .filter(([, taskUid]) => !runtimeTaskUids.has(taskUid))
      .map(([draftId]) => draftId),
  ]), [runtimeTaskUids, submittedTaskUidByDraftId, submittingDraftIds])

  useEffect(() => {
    const synchronizedDraftIds = new Set(
      [...submittedTaskUidByDraftId]
        .filter(([, taskUid]) => runtimeTaskUids.has(taskUid))
        .map(([draftId]) => draftId),
    )
    if (synchronizedDraftIds.size === 0) return

    const cleanupTimer = window.setTimeout(() => {
      setDrafts((current) => current.filter(
        (draft) => !synchronizedDraftIds.has(draft.id),
      ))
      setSubmittedTaskUidByDraftId((current) => {
        const next = new Map(current)
        synchronizedDraftIds.forEach((draftId) => next.delete(draftId))
        return next
      })
    }, 0)
    return () => window.clearTimeout(cleanupTimer)
  }, [runtimeTaskUids, submittedTaskUidByDraftId])

  function createDraft(
    point: NavigationPoint,
    priority: NavigationTaskPriority,
    videoSize: VideoSize | null,
  ) {
    const draft = createNavigationDraft(point, priority, videoSize)
    setDrafts((current) => [...current, draft])
    return draft
  }

  function changeDraftPriority(
    draftId: string,
    priority: NavigationTaskPriority,
  ) {
    setDrafts((current) => current.map((draft) => (
      draft.id === draftId ? { ...draft, priority } : draft
    )))
  }

  function removeDraft(draft: NavigationTask) {
    setDrafts((current) => current.filter((item) => item.id !== draft.id))
    toast.success("Đã xóa task nháp", {
      description: `Điểm đã chọn trên camera ${cameraName} đã được gỡ bỏ.`,
    })
  }

  async function submitDraft(draft: NavigationTask) {
    setSubmittingDraftIds((current) => new Set(current).add(draft.id))
    try {
      const createdTask = await robotTasksApi.create({
        camera_id: cameraId,
        target_pixel: { x: draft.pixelX, y: draft.pixelY },
        priority: draft.priority,
      })
      setSubmittedTaskUidByDraftId((current) => {
        const next = new Map(current)
        next.set(draft.id, createdTask.uid)
        return next
      })
      toast.success("Đã thêm task vào hàng đợi", {
        description: "Marker đang chờ runtime xác nhận.",
      })
      return true
    } catch (error) {
      toast.error("Không thể thêm task", {
        description: error instanceof Error ? error.message : "Vui lòng thử lại.",
      })
      return false
    } finally {
      setSubmittingDraftIds((current) => {
        const next = new Set(current)
        next.delete(draft.id)
        return next
      })
    }
  }

  async function cancelRuntimeTask(task: NavigationTask) {
    setRequestedCancelTaskIds((current) => new Set(current).add(task.id))
    try {
      await robotTasksApi.cancel(task.id)
      toast.success(`Đã yêu cầu hủy Task #${task.displayId}`, {
        description: "Đang chờ runtime xác nhận trạng thái task.",
      })
      return true
    } catch (error) {
      setRequestedCancelTaskIds((current) => {
        const next = new Set(current)
        next.delete(task.id)
        return next
      })
      toast.error(`Không thể hủy Task #${task.displayId}`, {
        description: error instanceof Error ? error.message : "Vui lòng thử lại.",
      })
      return false
    }
  }

  return {
    drafts: visibleDrafts,
    submittingDraftIds: pendingDraftIds,
    cancelingTaskIds,
    createDraft,
    changeDraftPriority,
    removeDraft,
    submitDraft,
    cancelRuntimeTask,
  }
}
