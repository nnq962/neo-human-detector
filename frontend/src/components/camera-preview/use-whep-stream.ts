import { useEffect, useState, type RefObject } from "react"
import type { StreamStatus, VideoSize } from "./types"
import {
  generateSdpFragment,
  getSessionUrl,
  getWhepUrl,
  parseIceServers,
  parseOffer,
} from "./whep"

const STREAM_RECONNECT_DELAY_MS = 3000
const EMPTY_VIDEO_SIZE: VideoSize = { width: 0, height: 0 }

interface WhepStreamState {
  status: StreamStatus
  errorMessage: string
  resolution: string
  videoSize: VideoSize
}

interface UseWhepStreamOptions {
  src: string
  reconnectKey: number
  videoRef: RefObject<HTMLVideoElement | null>
  onVideoSizeChange?: (size: VideoSize | null) => void
}

export function useWhepStream({
  src,
  reconnectKey,
  videoRef,
  onVideoSizeChange,
}: UseWhepStreamOptions): WhepStreamState {
  const endpointUrl = getWhepUrl(src)
  const [state, setState] = useState<WhepStreamState>({
    status: "connecting",
    errorMessage: "",
    resolution: "Detecting...",
    videoSize: EMPTY_VIDEO_SIZE,
  })

  useEffect(() => {
    const video = videoRef.current
    if (!video || !endpointUrl) {
      onVideoSizeChange?.(null)
      return
    }

    let disposed = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let cleanupConnection: (() => void) | null = null
    let attempt = 0

    const updateResolution = () => {
      const videoSize = { width: video.videoWidth, height: video.videoHeight }
      setState((current) => ({
        ...current,
        resolution: videoSize.width > 0 && videoSize.height > 0
          ? `${videoSize.width} × ${videoSize.height}`
          : "Detecting...",
        videoSize,
      }))
      onVideoSizeChange?.(
        videoSize.width > 0 && videoSize.height > 0 ? videoSize : null,
      )
    }

    const clearReconnectTimer = () => {
      if (!reconnectTimer) return
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    const closeCurrentConnection = () => {
      const cleanup = cleanupConnection
      cleanupConnection = null
      cleanup?.()
    }

    const scheduleReconnect = (reason: string) => {
      if (disposed) return
      setState((current) => ({
        ...current,
        status: "error",
        resolution: "Unavailable",
        errorMessage: `${reason}. Đang thử kết nối lại...`,
      }))
      clearReconnectTimer()
      closeCurrentConnection()
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        void connect()
      }, STREAM_RECONNECT_DELAY_MS)
    }

    const connect = async (): Promise<void> => {
      if (disposed) return
      clearReconnectTimer()
      closeCurrentConnection()

      attempt += 1
      setState((current) => ({
        ...current,
        status: "connecting",
        errorMessage: attempt > 1 ? "Đang thử kết nối lại..." : "",
        resolution: "Detecting...",
      }))

      let connectionClosed = false
      let sessionUrl = ""
      let offerData: ReturnType<typeof parseOffer> | null = null
      const queuedCandidates: RTCIceCandidate[] = []
      const connection = new RTCPeerConnection()

      cleanupConnection = () => {
        connectionClosed = true
        if (sessionUrl) {
          fetch(sessionUrl, { method: "DELETE" }).catch(() => undefined)
        }
        connection.getSenders().forEach((sender) => sender.track?.stop())
        connection.getReceivers().forEach((receiver) => receiver.track?.stop())
        connection.close()
        video.pause()
        video.srcObject = null
      }

      const sendCandidates = (candidates: RTCIceCandidate[]) => {
        if (!offerData || !sessionUrl || !candidates.length) return
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
        const optionsResponse = await fetch(endpointUrl, { method: "OPTIONS" })
        const iceServers = parseIceServers(optionsResponse.headers.get("link"))
        if (iceServers.length) connection.setConfiguration({ iceServers })

        connection.addTransceiver("video", { direction: "recvonly" })
        connection.addTransceiver("audio", { direction: "recvonly" })
        connection.createDataChannel("")

        connection.ontrack = (event) => {
          if (!disposed && !connectionClosed) video.srcObject = event.streams[0]
        }
        connection.onconnectionstatechange = () => {
          if (disposed || connectionClosed) return
          if (connection.connectionState === "connected") {
            setState((current) => ({
              ...current,
              status: "live",
              errorMessage: "",
            }))
            return
          }
          if (["failed", "disconnected", "closed"].includes(connection.connectionState)) {
            scheduleReconnect(`WebRTC ${connection.connectionState}`)
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
        offerData = parseOffer(offer.sdp ?? "")
        await connection.setLocalDescription(offer)

        const response = await fetch(endpointUrl, {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          body: offer.sdp,
        })
        if (!response.ok) throw new Error(`WHEP thất bại: HTTP ${response.status}`)

        sessionUrl = getSessionUrl(response, endpointUrl)
        await connection.setRemoteDescription({
          type: "answer",
          sdp: await response.text(),
        })
        sendCandidates(queuedCandidates.splice(0))
        if (!disposed && !connectionClosed) await video.play()
      } catch (error) {
        if (disposed || connectionClosed) return
        scheduleReconnect(
          error instanceof Error ? error.message : "Không thể mở stream",
        )
      }
    }

    video.addEventListener("loadedmetadata", updateResolution)
    video.addEventListener("resize", updateResolution)
    void connect()
    return () => {
      disposed = true
      clearReconnectTimer()
      video.removeEventListener("loadedmetadata", updateResolution)
      video.removeEventListener("resize", updateResolution)
      closeCurrentConnection()
    }
  }, [endpointUrl, reconnectKey, videoRef, onVideoSizeChange])

  if (!endpointUrl) {
    return {
      status: "error",
      errorMessage: "Thiếu stream URL",
      resolution: "Unavailable",
      videoSize: EMPTY_VIDEO_SIZE,
    }
  }
  return state
}
