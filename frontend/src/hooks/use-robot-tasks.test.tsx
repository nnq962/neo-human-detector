import { StrictMode, type PropsWithChildren } from "react"
import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const getSnapshotMock = vi.hoisted(() => vi.fn())

vi.mock("@/api/robot-tasks.api", () => ({
  robotTasksApi: {
    getSnapshot: getSnapshotMock,
  },
}))

import { useRobotTasks } from "./use-robot-tasks"

class FakeWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: FakeWebSocket[] = []

  readonly url: string
  readyState = FakeWebSocket.CONNECTING
  closeCalls = 0
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string | URL) {
    this.url = String(url)
    FakeWebSocket.instances.push(this)
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.(new Event("open"))
  }

  close(): void {
    if (this.readyState === FakeWebSocket.CLOSED) return
    this.closeCalls += 1
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.(new CloseEvent("close"))
  }
}

function StrictModeWrapper({ children }: PropsWithChildren) {
  return <StrictMode>{children}</StrictMode>
}

describe("useRobotTasks", () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    getSnapshotMock.mockImplementation(() => new Promise(() => undefined))
    vi.stubGlobal("WebSocket", FakeWebSocket)
  })

  it("đóng kết nối cũ và chỉ giữ socket của effect StrictMode hiện tại", () => {
    const firstMount = renderHook(() => useRobotTasks(), {
      wrapper: StrictModeWrapper,
    })
    expect(FakeWebSocket.instances).toHaveLength(1)
    const discardedSocket = FakeWebSocket.instances[0]
    firstMount.unmount()

    const { result, unmount } = renderHook(() => useRobotTasks(), {
      wrapper: StrictModeWrapper,
    })
    expect(FakeWebSocket.instances).toHaveLength(2)
    const activeSocket = FakeWebSocket.instances[1]

    act(() => discardedSocket.open())
    expect(discardedSocket.closeCalls).toBe(1)
    expect(result.current.connected).toBe(false)

    act(() => activeSocket.open())
    expect(activeSocket.closeCalls).toBe(0)
    expect(result.current.connected).toBe(true)

    unmount()
    expect(activeSocket.closeCalls).toBe(1)
  })
})
