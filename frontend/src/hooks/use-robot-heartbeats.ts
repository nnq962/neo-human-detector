import { useEffect, useState } from "react"
import type { RobotHeartbeatSnapshot } from "@/api/uart.api"
import { subscribeRobotHeartbeats } from "@/lib/robot-heartbeat-stream"

export function useRobotHeartbeats() {
  const [snapshot, setSnapshot] = useState<RobotHeartbeatSnapshot | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => subscribeRobotHeartbeats((state) => {
    setSnapshot(state.snapshot)
    setConnected(state.connected)
  }), [])

  return { snapshot, connected }
}
