import { useEffect, useRef, useState, type RefObject } from "react"
import type { VideoSize } from "./types"
import { getWhepUrl } from "./whep"
import {
  reconnectWhepStream,
  subscribeWhepStream,
  type WhepStreamSnapshot,
} from "./whep-stream-pool"

const EMPTY_VIDEO_SIZE: VideoSize = { width: 0, height: 0 }
const EMPTY_STREAM_SNAPSHOT: WhepStreamSnapshot = {
  status: "connecting",
  errorMessage: "",
  stream: null,
}

interface WhepStreamState {
  status: WhepStreamSnapshot["status"]
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
  const previousReconnectKeyRef = useRef(reconnectKey)
  const onVideoSizeChangeRef = useRef(onVideoSizeChange)
  const [streamSnapshot, setStreamSnapshot] = useState<WhepStreamSnapshot>(
    EMPTY_STREAM_SNAPSHOT,
  )
  const [videoSize, setVideoSize] = useState<VideoSize>(EMPTY_VIDEO_SIZE)

  useEffect(() => {
    onVideoSizeChangeRef.current = onVideoSizeChange
  }, [onVideoSizeChange])

  useEffect(() => {
    if (!endpointUrl) return
    const shouldReconnect = previousReconnectKeyRef.current !== reconnectKey
    previousReconnectKeyRef.current = reconnectKey
    const unsubscribe = subscribeWhepStream(endpointUrl, setStreamSnapshot)
    if (shouldReconnect) reconnectWhepStream(endpointUrl)
    return unsubscribe
  }, [endpointUrl, reconnectKey])

  useEffect(() => {
    const video = videoRef.current
    const stream = streamSnapshot.stream
    if (!video || !stream) {
      setVideoSize(EMPTY_VIDEO_SIZE)
      onVideoSizeChangeRef.current?.(null)
      return
    }

    const updateResolution = () => {
      const nextVideoSize = {
        width: video.videoWidth,
        height: video.videoHeight,
      }
      setVideoSize(nextVideoSize)
      onVideoSizeChangeRef.current?.(
        nextVideoSize.width > 0 && nextVideoSize.height > 0
          ? nextVideoSize
          : null,
      )
    }

    video.srcObject = stream
    video.addEventListener("loadedmetadata", updateResolution)
    video.addEventListener("resize", updateResolution)
    updateResolution()
    void video.play().catch(() => undefined)

    return () => {
      video.removeEventListener("loadedmetadata", updateResolution)
      video.removeEventListener("resize", updateResolution)
      if (video.srcObject === stream) {
        video.pause()
        video.srcObject = null
      }
      onVideoSizeChangeRef.current?.(null)
    }
  }, [streamSnapshot.stream, videoRef])

  if (!endpointUrl) {
    return {
      status: "error",
      errorMessage: "Thiếu stream URL",
      resolution: "Unavailable",
      videoSize: EMPTY_VIDEO_SIZE,
    }
  }

  return {
    status: streamSnapshot.status,
    errorMessage: streamSnapshot.errorMessage,
    resolution: videoSize.width > 0 && videoSize.height > 0
      ? `${videoSize.width} × ${videoSize.height}`
      : streamSnapshot.status === "error" ? "Unavailable" : "Detecting...",
    videoSize,
  }
}
