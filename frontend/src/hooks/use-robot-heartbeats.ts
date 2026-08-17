import { useEffect, useState } from "react"
import type { RobotHeartbeatSnapshot } from "@/api/uart.api"
import {
  subscribePublicRobotHeartbeats,
  subscribeRobotHeartbeats,
} from "@/lib/robot-heartbeat-stream"

export function useRobotHeartbeats(publicAccess = false) {
  const [snapshot, setSnapshot] = useState<RobotHeartbeatSnapshot | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const subscribe = publicAccess
      ? subscribePublicRobotHeartbeats
      : subscribeRobotHeartbeats
    return subscribe((state) => {
      setSnapshot(state.snapshot)
      setConnected(state.connected)
    })
  }, [publicAccess])

  return { snapshot, connected }
}
