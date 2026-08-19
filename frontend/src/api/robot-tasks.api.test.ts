import { beforeEach, describe, expect, it, vi } from "vitest"

import { robotTasksApi } from "@/api/robot-tasks.api"

const fetchMock = vi.fn()

function successResponse(uid: string) {
  return new Response(JSON.stringify({
    success: true,
    message: "OK",
    data: { uid },
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

describe("robotTasksApi", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })

  it("gửi draft tới đúng endpoint tạo task runtime", async () => {
    fetchMock.mockResolvedValue(successResponse("session:manual-1"))

    const result = await robotTasksApi.create({
      camera_id: "camera-1",
      target_pixel: { x: 960, y: 540 },
      priority: "high",
    })

    expect(result).toEqual({ uid: "session:manual-1" })
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runtime/tasks",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({
          camera_id: "camera-1",
          target_pixel: { x: 960, y: 540 },
          priority: "high",
        }),
      }),
    )
  })

  it("mã hóa UID và gọi đúng endpoint cancel", async () => {
    fetchMock.mockResolvedValue(successResponse("session:task-1"))

    const result = await robotTasksApi.cancel("session:task-1")

    expect(result).toEqual({ uid: "session:task-1" })
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runtime/tasks/session%3Atask-1/cancel",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
      }),
    )
  })
})
