import type { StreamStatus } from "./types"
import {
  generateSdpFragment,
  getSessionUrl,
  parseIceServers,
  parseOffer,
} from "./whep"

const STREAM_RECONNECT_DELAY_MS = 3000
const STREAM_IDLE_TTL_MS = 30_000
const MAX_IDLE_STREAMS = 4

export interface WhepStreamSnapshot {
  status: StreamStatus
  errorMessage: string
  stream: MediaStream | null
}

type StreamListener = (snapshot: WhepStreamSnapshot) => void

interface WhepStreamEntry {
  endpointUrl: string
  snapshot: WhepStreamSnapshot
  listeners: Set<StreamListener>
  idleSince: number | null
  idleTimer: ReturnType<typeof setTimeout> | null
  reconnectTimer: ReturnType<typeof setTimeout> | null
  cleanupConnection: (() => void) | null
  disposed: boolean
  attempt: number
}

const streamEntries = new Map<string, WhepStreamEntry>()
let idleLimitTimer: ReturnType<typeof setTimeout> | null = null

function notify(entry: WhepStreamEntry) {
  entry.listeners.forEach((listener) => listener(entry.snapshot))
}

function updateSnapshot(
  entry: WhepStreamEntry,
  next: Partial<WhepStreamSnapshot>,
) {
  entry.snapshot = { ...entry.snapshot, ...next }
  notify(entry)
}

function clearIdleTimer(entry: WhepStreamEntry) {
  if (!entry.idleTimer) return
  clearTimeout(entry.idleTimer)
  entry.idleTimer = null
}

function clearReconnectTimer(entry: WhepStreamEntry) {
  if (!entry.reconnectTimer) return
  clearTimeout(entry.reconnectTimer)
  entry.reconnectTimer = null
}

function closeCurrentConnection(entry: WhepStreamEntry) {
  const cleanup = entry.cleanupConnection
  entry.cleanupConnection = null
  cleanup?.()
}

function deleteWhepSession(sessionUrl: string) {
  if (!sessionUrl) return
  fetch(sessionUrl, { method: "DELETE", keepalive: true }).catch(() => undefined)
}

function disposeEntry(entry: WhepStreamEntry) {
  if (entry.disposed) return
  entry.disposed = true
  clearIdleTimer(entry)
  clearReconnectTimer(entry)
  closeCurrentConnection(entry)
  if (streamEntries.get(entry.endpointUrl) === entry) {
    streamEntries.delete(entry.endpointUrl)
  }
}

function enforceIdleLimit() {
  const idleEntries = [...streamEntries.values()]
    .filter((entry) => entry.listeners.size === 0 && entry.idleSince !== null)
    .sort((left, right) => (left.idleSince ?? 0) - (right.idleSince ?? 0))

  idleEntries
    .slice(0, Math.max(0, idleEntries.length - MAX_IDLE_STREAMS))
    .forEach(disposeEntry)
}

function scheduleIdleLimitEnforcement() {
  if (idleLimitTimer) return
  idleLimitTimer = setTimeout(() => {
    idleLimitTimer = null
    enforceIdleLimit()
  }, 0)
}

function scheduleDisposal(entry: WhepStreamEntry) {
  clearIdleTimer(entry)
  entry.idleSince = Date.now()
  entry.idleTimer = setTimeout(() => disposeEntry(entry), STREAM_IDLE_TTL_MS)
  scheduleIdleLimitEnforcement()
}

function scheduleReconnect(entry: WhepStreamEntry, reason: string) {
  if (entry.disposed) return
  updateSnapshot(entry, {
    status: "error",
    errorMessage: `${reason}. Đang thử kết nối lại...`,
    stream: null,
  })
  clearReconnectTimer(entry)
  closeCurrentConnection(entry)
  entry.reconnectTimer = setTimeout(() => {
    entry.reconnectTimer = null
    void connect(entry)
  }, STREAM_RECONNECT_DELAY_MS)
}

async function connect(entry: WhepStreamEntry): Promise<void> {
  if (entry.disposed) return
  clearReconnectTimer(entry)
  closeCurrentConnection(entry)

  entry.attempt += 1
  updateSnapshot(entry, {
    status: "connecting",
    errorMessage: entry.attempt > 1 ? "Đang thử kết nối lại..." : "",
    stream: null,
  })

  let connectionClosed = false
  let sessionUrl = ""
  let offerData: ReturnType<typeof parseOffer> | null = null
  const queuedCandidates: RTCIceCandidate[] = []
  const connection = new RTCPeerConnection()

  entry.cleanupConnection = () => {
    connectionClosed = true
    deleteWhepSession(sessionUrl)
    connection.getSenders().forEach((sender) => sender.track?.stop())
    connection.getReceivers().forEach((receiver) => receiver.track?.stop())
    connection.close()
  }

  const sendCandidates = (candidates: RTCIceCandidate[]) => {
    if (connectionClosed || !offerData || !sessionUrl || !candidates.length) {
      return
    }
    fetch(sessionUrl, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/trickle-ice-sdpfrag",
        "If-Match": "*",
      },
      body: generateSdpFragment(offerData, candidates),
    }).catch(() => undefined)
  }

  try {
    const optionsResponse = await fetch(entry.endpointUrl, { method: "OPTIONS" })
    if (!optionsResponse.ok) {
      throw new Error(`WHEP OPTIONS thất bại: HTTP ${optionsResponse.status}`)
    }
    if (connectionClosed) return
    const iceServers = parseIceServers(optionsResponse.headers.get("link"))
    if (iceServers.length) connection.setConfiguration({ iceServers })

    connection.addTransceiver("video", { direction: "recvonly" })
    connection.addTransceiver("audio", { direction: "recvonly" })
    connection.createDataChannel("")

    connection.ontrack = (event) => {
      if (entry.disposed || connectionClosed) return
      updateSnapshot(entry, { stream: event.streams[0] ?? null })
    }
    connection.onconnectionstatechange = () => {
      if (entry.disposed || connectionClosed) return
      if (connection.connectionState === "connected") {
        updateSnapshot(entry, { status: "live", errorMessage: "" })
        return
      }
      if (["failed", "disconnected", "closed"].includes(connection.connectionState)) {
        scheduleReconnect(entry, `WebRTC ${connection.connectionState}`)
      }
    }
    connection.onicecandidate = (event) => {
      if (!event.candidate) return
      if (!sessionUrl) {
        queuedCandidates.push(event.candidate)
        return
      }
      sendCandidates([event.candidate])
    }

    const offer = await connection.createOffer()
    if (connectionClosed) return
    offerData = parseOffer(offer.sdp ?? "")
    await connection.setLocalDescription(offer)
    if (connectionClosed) return

    const response = await fetch(entry.endpointUrl, {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: offer.sdp,
    })
    if (!response.ok) throw new Error(`WHEP thất bại: HTTP ${response.status}`)

    const createdSessionUrl = getSessionUrl(response, entry.endpointUrl)
    sessionUrl = createdSessionUrl
    if (connectionClosed) {
      deleteWhepSession(createdSessionUrl)
      return
    }
    await connection.setRemoteDescription({
      type: "answer",
      sdp: await response.text(),
    })
    sendCandidates(queuedCandidates.splice(0))
  } catch (error) {
    if (entry.disposed || connectionClosed) return
    scheduleReconnect(
      entry,
      error instanceof Error ? error.message : "Không thể mở stream",
    )
  }
}

function createEntry(endpointUrl: string) {
  const entry: WhepStreamEntry = {
    endpointUrl,
    snapshot: {
      status: "connecting",
      errorMessage: "",
      stream: null,
    },
    listeners: new Set(),
    idleSince: null,
    idleTimer: null,
    reconnectTimer: null,
    cleanupConnection: null,
    disposed: false,
    attempt: 0,
  }
  streamEntries.set(endpointUrl, entry)
  void connect(entry)
  return entry
}

export function subscribeWhepStream(
  endpointUrl: string,
  listener: StreamListener,
) {
  const entry = streamEntries.get(endpointUrl) ?? createEntry(endpointUrl)
  clearIdleTimer(entry)
  entry.idleSince = null
  entry.listeners.add(listener)
  listener(entry.snapshot)

  return () => {
    entry.listeners.delete(listener)
    if (entry.listeners.size === 0) scheduleDisposal(entry)
  }
}

export function reconnectWhepStream(endpointUrl: string) {
  const entry = streamEntries.get(endpointUrl)
  if (entry) void connect(entry)
}
