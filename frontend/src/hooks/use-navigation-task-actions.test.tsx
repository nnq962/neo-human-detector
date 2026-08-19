import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { RobotTask } from "@/api/robot-tasks.api"
import type { NavigationTask } from "@/lib/navigation-tasks"

const createTaskMock = vi.hoisted(() => vi.fn())
const cancelTaskMock = vi.hoisted(() => vi.fn())

vi.mock("@/api/robot-tasks.api", () => ({
  robotTasksApi: {
    create: createTaskMock,
    cancel: cancelTaskMock,
  },
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

import { useNavigationTaskActions } from "./use-navigation-task-actions"

const RUNTIME_TASK: RobotTask = {
  uid: "session:task-1",
  task_id: null,
  robot_id: null,
  camera_id: "camera-1",
  camera_name: "Camera 1",
  zone_id: "zone-1",
  zone_name: "Zone 1",
  origin: "zone",
  priority: "high",
  target_pixel: { x: 960, y: 540 },
  goal_pose: { x: 1, y: 2, theta: 0 },
  person_global_id: null,
  person_similarity: null,
  person_track_id: null,
  status: "WAITING_ROBOT",
  retry_count: 0,
  assigned_at: "2026-08-19T00:00:00.000Z",
  updated_at: "2026-08-19T00:00:00.000Z",
  completed_at: null,
}

const NAVIGATION_RUNTIME_TASK: NavigationTask = {
  id: RUNTIME_TASK.uid,
  displayId: "task-1",
  kind: "runtime",
  origin: "zone",
  zoneName: "Zone 1",
  x: 50,
  y: 50,
  pixelX: 960,
  pixelY: 540,
  createdAt: new Date(RUNTIME_TASK.assigned_at),
  completedAt: null,
  isFading: false,
  priority: "high",
  status: "pending",
}

describe("useNavigationTaskActions", () => {
  beforeEach(() => {
    createTaskMock.mockReset()
    cancelTaskMock.mockReset()
  })

  it("giữ draft sau POST và thay liền mạch khi WebSocket có task thật", async () => {
    createTaskMock.mockResolvedValue({ uid: "session:new-task" })
    const initialProps: { runtimeTasks: RobotTask[] } = { runtimeTasks: [] }
    const { result, rerender } = renderHook(
      ({ runtimeTasks }: { runtimeTasks: RobotTask[] }) => (
        useNavigationTaskActions({
          cameraId: "camera-1",
          cameraName: "Camera 1",
          runtimeTasks,
        })
      ),
      { initialProps },
    )

    let draft!: NavigationTask
    act(() => {
      draft = result.current.createDraft(
        { x: 50, y: 50 },
        "medium",
        { width: 1920, height: 1080 },
      )
    })
    expect(result.current.drafts).toHaveLength(1)

    await act(async () => {
      await result.current.submitDraft(draft)
    })

    expect(createTaskMock).toHaveBeenCalledWith({
      camera_id: "camera-1",
      target_pixel: { x: 960, y: 540 },
      priority: "medium",
    })
    expect(result.current.drafts).toHaveLength(1)
    expect(result.current.submittingDraftIds.has(draft.id)).toBe(true)

    rerender({
      runtimeTasks: [{
        ...RUNTIME_TASK,
        uid: "session:new-task",
        origin: "manual",
        zone_id: null,
        zone_name: null,
      }],
    })

    expect(result.current.drafts).toEqual([])
    expect(result.current.submittingDraftIds.has(draft.id)).toBe(false)
  })

  it("đánh dấu canceling ngay khi gọi API và chờ WebSocket xác nhận", async () => {
    let resolveCancel: ((value: { uid: string }) => void) | undefined
    cancelTaskMock.mockImplementation(() => new Promise((resolve) => {
      resolveCancel = resolve
    }))
    const { result, rerender } = renderHook(
      ({ runtimeTasks }: { runtimeTasks: RobotTask[] }) => (
        useNavigationTaskActions({
          cameraId: "camera-1",
          cameraName: "Camera 1",
          runtimeTasks,
        })
      ),
      { initialProps: { runtimeTasks: [RUNTIME_TASK] } },
    )

    let cancelPromise: Promise<boolean>
    act(() => {
      cancelPromise = result.current.cancelRuntimeTask(NAVIGATION_RUNTIME_TASK)
    })
    expect(result.current.cancelingTaskIds.has(RUNTIME_TASK.uid)).toBe(true)
    expect(cancelTaskMock).toHaveBeenCalledWith(RUNTIME_TASK.uid)

    await act(async () => {
      resolveCancel?.({ uid: RUNTIME_TASK.uid })
      await cancelPromise
    })
    expect(result.current.cancelingTaskIds.has(RUNTIME_TASK.uid)).toBe(true)

    rerender({
      runtimeTasks: [{ ...RUNTIME_TASK, status: "CANCELING" }],
    })
    expect(result.current.cancelingTaskIds.has(RUNTIME_TASK.uid)).toBe(false)
  })
})
