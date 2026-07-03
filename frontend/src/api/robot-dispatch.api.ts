export type RobotDispatchEventType = "sent" | "skipped" | "service_update"
export type RobotDispatchAction = "invite" | "clear" | "serving" | "served" | "failed"
export type RobotDispatchReason = "already_requested" | "already_served" | string

export interface RobotDispatchZone {
  camera_id: string
  camera_name: string
  zone_id: string | null
  zone_name: string
  state: string
}

export interface RobotDispatchPerson {
  global_id: number
  track_id?: number
  similarity?: number
  reid_status?: string
}

export interface RobotDispatchEvent {
  sequence: number
  timestamp: number
  type: RobotDispatchEventType
  action: RobotDispatchAction
  request_id?: string
  reason?: RobotDispatchReason
  zone: RobotDispatchZone
  person: RobotDispatchPerson | null
}

export function getRobotDispatchEventsWsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/robot-dispatch/events`
}
