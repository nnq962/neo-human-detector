import { describe, expect, it } from "vitest"
import type { Camera } from "@/api/cameras.api"
import type { RobotTask, RobotTaskStatus } from "@/api/robot-tasks.api"
import {
  mapRuntimeTaskStatus,
  mapRuntimeTaskToNavigation,
} from "@/lib/navigation-tasks"

const CAMERA: Camera = {
  id: "camera-1",
  name: "Camera 1",
  enabled: true,
  stream: {
    source: "rtsp://example.local/1",
    protocol: "tcp",
    on_demand: true,
  },
  zones: [
    {
      id: "zone-1",
      name: "Zone 1",
      priority: "high",
      service_point: [960, 540],
      points: [[0, 0], [100, 0], [100, 100]],
    },
  ],
}

function createTask(overrides: Partial<RobotTask> = {}): RobotTask {
  return {
    uid: "session:task-1",
    task_id: 7,
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
    ...overrides,
  }
}

describe("Navigation runtime task mapping", () => {
  it.each<[RobotTaskStatus, ReturnType<typeof mapRuntimeTaskStatus>]>([
    ["WAITING_ROBOT", "pending"],
    ["ASSIGNING", "pending"],
    ["ASSIGNED", "active"],
    ["IN_PROGRESS", "active"],
    ["CANCELING", "canceling"],
    ["COMPLETED", "done"],
    ["FAILED", "error"],
    ["CANCELED", null],
  ])("ánh xạ %s thành %s", (status, expected) => {
    expect(mapRuntimeTaskStatus(status)).toBe(expected)
  })

  it("đặt marker theo tọa độ pixel của video nguồn", () => {
    const mapped = mapRuntimeTaskToNavigation(
      createTask(),
      CAMERA,
      { width: 1920, height: 1080 },
      Date.parse("2026-08-19T00:00:01.000Z"),
    )

    expect(mapped).toMatchObject({
      x: 50,
      y: 50,
      pixelX: 960,
      pixelY: 540,
      origin: "zone",
      priority: "high",
      status: "pending",
    })
  })

  it("làm mờ sau 10 giây và ẩn task hoàn thành sau 11 giây", () => {
    const completedTask = createTask({
      status: "COMPLETED",
      completed_at: "2026-08-19T00:00:00.000Z",
    })

    expect(mapRuntimeTaskToNavigation(
      completedTask,
      CAMERA,
      { width: 1920, height: 1080 },
      Date.parse("2026-08-19T00:00:10.500Z"),
    )?.isFading).toBe(true)
    expect(mapRuntimeTaskToNavigation(
      completedTask,
      CAMERA,
      { width: 1920, height: 1080 },
      Date.parse("2026-08-19T00:00:11.000Z"),
    )).toBeNull()
  })
})
