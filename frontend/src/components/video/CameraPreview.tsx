import { useEffect, useRef, useState } from 'react'
import { Canvas, Circle, FabricText, Point, Polygon, Polyline, controlsUtils } from 'fabric'
import { useDetectionBoxes } from '../../hooks/useDetectionBoxes'
import type { Zone } from '../../types/config'
import type { DetectionBoxesPayload, DetectionZoneStatus } from '../../types/detection'

type CameraPreviewProps = {
    src: string
    reconnectKey?: number
    zones?: Zone[]
    detectionZones?: Zone[]
    selectedZoneIndex?: number | null
    showZonesOverlay?: boolean
    isEditingVertices?: boolean
    isAddingZone?: boolean
    onZoneSelect?: (zoneIndex: number) => void
    onZonePointsChange?: (zoneIndex: number, points: number[][]) => void
    onZoneAdd?: (points: number[][]) => void
}

type StreamStatus = 'connecting' | 'live' | 'error'

type PreviewSize = {
    width: number
    height: number
}

type VideoSize = {
    width: number
    height: number
}

type OfferData = {
    iceUfrag: string
    icePwd: string
    medias: string[]
}

const DOUBLE_TAP_MAX_DELAY_MS = 350
const DOUBLE_TAP_MAX_DISTANCE_PX = 28

function getWhepUrl(src: string) {
    const trimmedSrc = src.trim()

    if (!trimmedSrc) {
        return ''
    }

    return trimmedSrc.endsWith('/whep') ? trimmedSrc : `${trimmedSrc.replace(/\/$/, '')}/whep`
}

function unquote(value: string) {
    return value.trim().replace(/^"|"$/g, '')
}

function parseIceServers(linkHeader: string | null): RTCIceServer[] {
    if (!linkHeader) {
        return []
    }

    return linkHeader
        .split(',')
        .map((entry) => {
            const urlMatch = entry.match(/<([^>]+)>/)

            if (!urlMatch) {
                return null
            }

            const server: RTCIceServer = { urls: urlMatch[1] }

            entry.split(';').forEach((part) => {
                const [rawKey, rawValue] = part.split('=')
                const key = rawKey?.trim()
                const value = rawValue ? unquote(rawValue) : ''

                if (key === 'username') {
                    server.username = value
                }

                if (key === 'credential') {
                    server.credential = value
                }
            })

            return server
        })
        .filter((server): server is RTCIceServer => Boolean(server))
}

function getSessionUrl(response: Response, endpointUrl: string) {
    const location = response.headers.get('location')

    if (!location) {
        return ''
    }

    return new URL(location, endpointUrl).toString()
}

function parseOffer(sdp: string): OfferData {
    const offerData: OfferData = {
        iceUfrag: '',
        icePwd: '',
        medias: [],
    }

    sdp.split('\r\n').forEach((line) => {
        if (line.startsWith('m=')) {
            offerData.medias.push(line.slice('m='.length))
        }

        if (!offerData.iceUfrag && line.startsWith('a=ice-ufrag:')) {
            offerData.iceUfrag = line.slice('a=ice-ufrag:'.length)
        }

        if (!offerData.icePwd && line.startsWith('a=ice-pwd:')) {
            offerData.icePwd = line.slice('a=ice-pwd:'.length)
        }
    })

    return offerData
}

function generateSdpFragment(offerData: OfferData, candidates: RTCIceCandidate[]) {
    const candidatesByMedia = new Map<number, RTCIceCandidate[]>()

    candidates.forEach((candidate) => {
        const mid = candidate.sdpMLineIndex

        if (mid === null) {
            return
        }

        const currentCandidates = candidatesByMedia.get(mid) ?? []
        currentCandidates.push(candidate)
        candidatesByMedia.set(mid, currentCandidates)
    })

    let fragment = `a=ice-ufrag:${offerData.iceUfrag}\r\na=ice-pwd:${offerData.icePwd}\r\n`

    offerData.medias.forEach((media, mid) => {
        const candidatesForMedia = candidatesByMedia.get(mid)

        if (!candidatesForMedia) {
            return
        }

        fragment += `m=${media}\r\na=mid:${mid}\r\n`

        candidatesForMedia.forEach((candidate) => {
            fragment += `a=${candidate.candidate}\r\n`
        })
    })

    return fragment
}

function formatResolution(width: number, height: number) {
    return width > 0 && height > 0 ? `${width} x ${height}` : 'Detecting...'
}

function getAbsolutePolygonPoints(polygon: Polygon) {
    const transform = polygon.calcTransformMatrix()

    return polygon.points.map((polygonPoint) =>
        new Point(
            polygonPoint.x - polygon.pathOffset.x,
            polygonPoint.y - polygon.pathOffset.y,
        ).transform(transform),
    )
}

function getContainedVideoRect(previewSize: PreviewSize, sourceSize: VideoSize) {
    if (previewSize.width === 0 || previewSize.height === 0 || sourceSize.width === 0 || sourceSize.height === 0) {
        return null
    }

    const scale = Math.min(
        previewSize.width / sourceSize.width,
        previewSize.height / sourceSize.height,
    )
    const width = sourceSize.width * scale
    const height = sourceSize.height * scale

    return {
        scale,
        width,
        height,
        offsetX: (previewSize.width - width) / 2,
        offsetY: (previewSize.height - height) / 2,
    }
}

const detectionZoneColors: Record<DetectionZoneStatus, { fill: string; stroke: string; label: string }> = {
    EMPTY: {
        fill: 'rgba(239, 68, 68, 0.18)',
        stroke: '#ef4444',
        label: 'EMPTY',
    },
    OCCUPIED: {
        fill: 'rgba(34, 197, 94, 0.18)',
        stroke: '#22c55e',
        label: 'OCCUPIED',
    },
    PENDING_ENTER: {
        fill: 'rgba(245, 158, 11, 0.2)',
        stroke: '#f59e0b',
        label: 'PENDING ENTER',
    },
    PENDING_EXIT: {
        fill: 'rgba(59, 130, 246, 0.2)',
        stroke: '#3b82f6',
        label: 'PENDING EXIT',
    },
}

const fallbackDetectionZoneColor = {
    fill: 'rgba(148, 163, 184, 0.16)',
    stroke: '#94a3b8',
    label: 'UNKNOWN',
}

function isDetectionZoneStatus(status: string | undefined): status is DetectionZoneStatus {
    return status === 'EMPTY' ||
        status === 'OCCUPIED' ||
        status === 'PENDING_ENTER' ||
        status === 'PENDING_EXIT'
}

function drawDetectionZones(
    context: CanvasRenderingContext2D,
    zones: Zone[],
    payload: DetectionBoxesPayload,
    sourceSize: VideoSize,
    videoRect: NonNullable<ReturnType<typeof getContainedVideoRect>>,
) {
    if (!payload.zones) {
        return
    }

    zones.forEach((zone) => {
        const status = payload.zones?.[zone.name]
        const color = isDetectionZoneStatus(status) ? detectionZoneColors[status] : fallbackDetectionZoneColor
        const points = zone.points.map(([x, y]) => ({
            x: videoRect.offsetX + (x / sourceSize.width) * videoRect.width,
            y: videoRect.offsetY + (y / sourceSize.height) * videoRect.height,
        }))

        if (points.length < 3) {
            return
        }

        context.beginPath()
        context.moveTo(points[0].x, points[0].y)
        points.slice(1).forEach((point) => context.lineTo(point.x, point.y))
        context.closePath()

        context.fillStyle = color.fill
        context.strokeStyle = color.stroke
        context.lineWidth = 2
        context.fill()
        context.stroke()

        const labelPoint = points.reduce(
            (current, point) => ({
                x: current.x + point.x / points.length,
                y: current.y + point.y / points.length,
            }),
            { x: 0, y: 0 },
        )
        const label = `${zone.name}`
        const labelWidth = context.measureText(label).width + 12
        const labelHeight = 22
        const labelX = Math.max(videoRect.offsetX, labelPoint.x - labelWidth / 2)
        const labelY = Math.max(videoRect.offsetY, labelPoint.y - labelHeight / 2)

        context.fillStyle = color.stroke
        context.fillRect(labelX, labelY, labelWidth, labelHeight)
        context.fillStyle = '#ffffff'
        context.fillText(label, labelX + 6, labelY + 5)
    })
}

function drawDetectionBoxes(
    canvas: HTMLCanvasElement,
    payload: DetectionBoxesPayload | null,
    zones: Zone[],
    shouldDrawZones: boolean,
    previewSize: PreviewSize,
    videoSize: VideoSize,
) {
    const context = canvas.getContext('2d')

    if (!context) {
        return
    }

    canvas.width = previewSize.width
    canvas.height = previewSize.height
    context.clearRect(0, 0, previewSize.width, previewSize.height)

    if (!payload) {
        return
    }

    const sourceSize = payload.resolution.width > 0 && payload.resolution.height > 0
        ? payload.resolution
        : videoSize
    const videoRect = getContainedVideoRect(previewSize, sourceSize)

    if (!videoRect) {
        return
    }

    context.lineWidth = 2
    context.font = '12px system-ui, -apple-system, sans-serif'
    context.textBaseline = 'top'

    if (shouldDrawZones) {
        drawDetectionZones(context, zones, payload, sourceSize, videoRect)
    }

    payload.objects.forEach((object) => {
        const [x, y, width, height] = object.bbox
        const boxX = videoRect.offsetX + x * videoRect.width
        const boxY = videoRect.offsetY + y * videoRect.height
        const boxWidth = width * videoRect.width
        const boxHeight = height * videoRect.height
        const label = `${(object.conf * 100).toFixed(0)}%`

        context.strokeStyle = '#22d3ee'
        context.fillStyle = 'rgba(34, 211, 238, 0.14)'
        context.strokeRect(boxX, boxY, boxWidth, boxHeight)
        context.fillRect(boxX, boxY, boxWidth, boxHeight)

        const labelWidth = context.measureText(label).width + 12
        const labelHeight = 22
        const labelY = Math.max(videoRect.offsetY, boxY - labelHeight)

        context.fillStyle = 'rgba(15, 23, 42, 0.4)'
        context.fillRect(boxX, labelY, labelWidth, labelHeight)
        context.fillStyle = '#ffffff'
        context.fillText(label, boxX + 6, labelY + 5)
    })
}

const zoneColors = [
    { fill: 'rgba(14, 165, 233, 0.22)', stroke: '#0ea5e9' },
    { fill: 'rgba(16, 185, 129, 0.22)', stroke: '#10b981' },
    { fill: 'rgba(245, 158, 11, 0.24)', stroke: '#f59e0b' },
    { fill: 'rgba(244, 63, 94, 0.22)', stroke: '#f43f5e' },
    { fill: 'rgba(139, 92, 246, 0.22)', stroke: '#8b5cf6' },
    { fill: 'rgba(236, 72, 153, 0.22)', stroke: '#ec4899' },
]

function CameraPreview({
    src,
    reconnectKey = 0,
    zones = [],
    detectionZones = zones,
    selectedZoneIndex = null,
    showZonesOverlay = true,
    isEditingVertices = false,
    isAddingZone = false,
    onZoneSelect,
    onZonePointsChange,
    onZoneAdd,
}: CameraPreviewProps) {
    const containerRef = useRef<HTMLDivElement | null>(null)
    const videoRef = useRef<HTMLVideoElement | null>(null)
    const detectionCanvasRef = useRef<HTMLCanvasElement | null>(null)
    const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null)
    const fabricCanvasRef = useRef<Canvas | null>(null)
    const isFinishingDraftRef = useRef(false)
    const draftPointsRef = useRef<number[][]>([])
    const lastDraftTapRef = useRef<{ time: number; x: number; y: number } | null>(null)
    const [status, setStatus] = useState<StreamStatus>('connecting')
    const [errorMessage, setErrorMessage] = useState('')
    const [resolution, setResolution] = useState('Detecting...')
    const [previewSize, setPreviewSize] = useState<PreviewSize>({ width: 0, height: 0 })
    const [videoSize, setVideoSize] = useState<VideoSize>({ width: 0, height: 0 })
    const [draftPoints, setDraftPoints] = useState<number[][]>([])
    const detectionBoxes = useDetectionBoxes()

    useEffect(() => {
        const canvasElement = overlayCanvasRef.current

        if (!canvasElement) {
            return undefined
        }

        const canvas = new Canvas(canvasElement, {
            selection: false,
            renderOnAddRemove: false,
        })

        canvas.defaultCursor = 'default'
        canvas.hoverCursor = 'default'
        canvas.wrapperEl.style.position = 'absolute'
        canvas.wrapperEl.style.inset = '0'
        canvas.wrapperEl.style.width = '100%'
        canvas.wrapperEl.style.height = '100%'
        canvas.wrapperEl.style.zIndex = '1'
        canvas.wrapperEl.style.pointerEvents = 'none'
        canvas.upperCanvasEl.style.pointerEvents = 'none'
        canvas.upperCanvasEl.style.touchAction = 'none'

        fabricCanvasRef.current = canvas

        return () => {
            fabricCanvasRef.current = null
            canvas.dispose()
        }
    }, [])

    useEffect(() => {
        const container = containerRef.current

        if (!container) {
            return undefined
        }

        const updatePreviewSize = () => {
            const rect = container.getBoundingClientRect()
            setPreviewSize({
                width: Math.round(rect.width),
                height: Math.round(rect.height),
            })
        }

        const resizeObserver = new ResizeObserver(updatePreviewSize)

        updatePreviewSize()
        resizeObserver.observe(container)

        return () => {
            resizeObserver.disconnect()
        }
    }, [])

    useEffect(() => {
        const canvas = fabricCanvasRef.current

        if (!canvas || previewSize.width === 0 || previewSize.height === 0) {
            return
        }

        canvas.setDimensions({
            width: previewSize.width,
            height: previewSize.height,
        })
        const isInteractive = isEditingVertices || isAddingZone

        canvas.wrapperEl.style.pointerEvents = isInteractive ? 'auto' : 'none'
        canvas.upperCanvasEl.style.pointerEvents = isInteractive ? 'auto' : 'none'
        canvas.defaultCursor = isAddingZone ? 'crosshair' : 'default'
        canvas.hoverCursor = isAddingZone ? 'crosshair' : isEditingVertices ? 'move' : 'default'

        canvas.clear()

        if (videoSize.width === 0 || videoSize.height === 0) {
            canvas.requestRenderAll()
            return
        }

        const scale = Math.min(
            previewSize.width / videoSize.width,
            previewSize.height / videoSize.height,
        )
        const renderedWidth = videoSize.width * scale
        const renderedHeight = videoSize.height * scale
        const offsetX = (previewSize.width - renderedWidth) / 2
        const offsetY = (previewSize.height - renderedHeight) / 2

        if (showZonesOverlay) {
            zones.forEach((zone, index) => {
                const color = zoneColors[index % zoneColors.length]
                const isSelected = index === selectedZoneIndex
                const points = zone.points.map(([x, y]) => ({
                    x: offsetX + x * scale,
                    y: offsetY + y * scale,
                }))

                if (points.length < 3) {
                    return
                }

                const polygon = new Polygon(points, {
                    fill: color.fill,
                    stroke: color.stroke,
                    strokeWidth: isSelected ? 3 : 2,
                    objectCaching: false,
                    selectable: isEditingVertices && isSelected,
                    evented: isEditingVertices,
                    hasControls: isEditingVertices && isSelected,
                    hasBorders: false,
                    lockScalingX: true,
                    lockScalingY: true,
                    lockRotation: true,
                    cornerColor: '#ffffff',
                    cornerStrokeColor: color.stroke,
                    cornerStyle: 'circle',
                    transparentCorners: false,
                    hoverCursor: isEditingVertices && isSelected ? 'move' : 'default',
                    moveCursor: 'move',
                })

                const syncPolygonPoints = () => {
                    if (!isEditingVertices || !isSelected) {
                        return
                    }

                    const nextPoints = getAbsolutePolygonPoints(polygon).map((point) => {
                        const imageX = Math.round((point.x - offsetX) / scale)
                        const imageY = Math.round((point.y - offsetY) / scale)

                        return [
                            Math.min(Math.max(imageX, 0), videoSize.width),
                            Math.min(Math.max(imageY, 0), videoSize.height),
                        ]
                    })

                    onZonePointsChange?.(index, nextPoints)
                }

                const labelPoint = points.reduce(
                    (current, point) => ({
                        x: current.x + point.x / points.length,
                        y: current.y + point.y / points.length,
                    }),
                    { x: 0, y: 0 },
                )

                const label = new FabricText(zone.name, {
                    left: labelPoint.x,
                    top: labelPoint.y,
                    originX: 'center',
                    originY: 'center',
                    fill: '#ffffff',
                    fontSize: 13,
                    fontWeight: '700',
                    backgroundColor: color.stroke,
                    padding: 5,
                    selectable: false,
                    evented: false,
                })

                const updateLabelPosition = () => {
                    const absolutePoints = getAbsolutePolygonPoints(polygon)
                    const nextLabelPoint = absolutePoints.reduce(
                        (current, point) => ({
                            x: current.x + point.x / absolutePoints.length,
                            y: current.y + point.y / absolutePoints.length,
                        }),
                        { x: 0, y: 0 },
                    )

                    label.set({
                        left: nextLabelPoint.x,
                        top: nextLabelPoint.y,
                    })
                    label.setCoords()
                    canvas.requestRenderAll()
                }

                if (isEditingVertices && isSelected) {
                    polygon.controls = controlsUtils.createPolyControls(polygon, {
                        cursorStyle: 'crosshair',
                        render: controlsUtils.renderCircleControl,
                        sizeX: 12,
                        sizeY: 12,
                    })
                    polygon.on('moving', updateLabelPosition)
                    polygon.on('modifyPoly', updateLabelPosition)
                    polygon.on('modified', syncPolygonPoints)
                }

                if (isEditingVertices) {
                    polygon.on('mousedown', () => onZoneSelect?.(index))
                }

                canvas.add(polygon, label)

                if (isEditingVertices && isSelected) {
                    canvas.setActiveObject(polygon)
                }
            })
        }

        if (isAddingZone && draftPoints.length > 0) {
            const color = zoneColors[zones.length % zoneColors.length]
            const draftCanvasPoints = draftPoints.map(([x, y]) => ({
                x: offsetX + x * scale,
                y: offsetY + y * scale,
            }))

            if (draftCanvasPoints.length > 1) {
                canvas.add(
                    new Polyline(draftCanvasPoints, {
                        fill: 'transparent',
                        stroke: color.stroke,
                        strokeWidth: 2,
                        strokeDashArray: [6, 4],
                        selectable: false,
                        evented: false,
                    }),
                )
            }

            draftCanvasPoints.forEach((point) => {
                canvas.add(
                    new Circle({
                        left: point.x,
                        top: point.y,
                        radius: 5,
                        fill: color.stroke,
                        stroke: '#ffffff',
                        strokeWidth: 2,
                        originX: 'center',
                        originY: 'center',
                        selectable: false,
                        evented: false,
                    }),
                )
            })
        }

        canvas.requestRenderAll()
    }, [
        previewSize,
        videoSize,
        zones,
        selectedZoneIndex,
        showZonesOverlay,
        isEditingVertices,
        isAddingZone,
        draftPoints,
        onZoneSelect,
        onZonePointsChange,
    ])

    useEffect(() => {
        const canvas = detectionCanvasRef.current

        if (!canvas || previewSize.width === 0 || previewSize.height === 0) {
            return
        }

        drawDetectionBoxes(canvas, detectionBoxes, detectionZones, !isEditingVertices, previewSize, videoSize)
    }, [detectionBoxes, detectionZones, isEditingVertices, previewSize, videoSize])

    useEffect(() => {
        const canvas = fabricCanvasRef.current

        if (!canvas || !isAddingZone || previewSize.width === 0 || previewSize.height === 0) {
            return undefined
        }

        if (videoSize.width === 0 || videoSize.height === 0) {
            return undefined
        }

        const scale = Math.min(
            previewSize.width / videoSize.width,
            previewSize.height / videoSize.height,
        )
        const renderedWidth = videoSize.width * scale
        const renderedHeight = videoSize.height * scale
        const offsetX = (previewSize.width - renderedWidth) / 2
        const offsetY = (previewSize.height - renderedHeight) / 2

        const canvasToImagePoint = (point: Point) => {
            const boundedX = Math.min(Math.max(point.x, offsetX), offsetX + renderedWidth)
            const boundedY = Math.min(Math.max(point.y, offsetY), offsetY + renderedHeight)

            return [
                Math.round((boundedX - offsetX) / scale),
                Math.round((boundedY - offsetY) / scale),
            ]
        }

        const isDoubleTap = (event: MouseEvent | PointerEvent | TouchEvent, point: Point) => {
            const now = event.timeStamp || Date.now()
            const lastTap = lastDraftTapRef.current

            if (!lastTap) {
                lastDraftTapRef.current = { time: now, x: point.x, y: point.y }
                return false
            }

            const elapsed = now - lastTap.time
            const distance = Math.hypot(point.x - lastTap.x, point.y - lastTap.y)

            lastDraftTapRef.current = { time: now, x: point.x, y: point.y }
            return elapsed <= DOUBLE_TAP_MAX_DELAY_MS && distance <= DOUBLE_TAP_MAX_DISTANCE_PX
        }

        const finishDraft = () => {
            if (isFinishingDraftRef.current) {
                return
            }

            isFinishingDraftRef.current = true
            const currentPoints = draftPointsRef.current

            if (currentPoints.length < 2) {
                isFinishingDraftRef.current = false
                return
            }

            draftPointsRef.current = []
            lastDraftTapRef.current = null
            setDraftPoints([])
            onZoneAdd?.(currentPoints)
        }

        const handleMouseDown = (event: { e: MouseEvent | PointerEvent | TouchEvent }) => {
            const point = canvas.getScenePoint(event.e)
            const nextPoint = canvasToImagePoint(point)
            const shouldFinishDraft = event.e.detail >= 2 || isDoubleTap(event.e, point)

            if (shouldFinishDraft) {
                finishDraft()
                return
            }

            const nextPoints = [...draftPointsRef.current, nextPoint]

            draftPointsRef.current = nextPoints
            setDraftPoints(nextPoints)
        }

        canvas.on('mouse:down', handleMouseDown)

        return () => {
            canvas.off('mouse:down', handleMouseDown)
        }
    }, [isAddingZone, previewSize, videoSize, onZoneAdd])

    useEffect(() => {
        if (!isAddingZone) {
            draftPointsRef.current = []
            setDraftPoints([])
            isFinishingDraftRef.current = false
            lastDraftTapRef.current = null
        }
    }, [isAddingZone])

    useEffect(() => {
        const endpointUrl = getWhepUrl(src)
        const video = videoRef.current

        if (!video) {
            return undefined
        }

        if (!endpointUrl) {
            setStatus('error')
            setErrorMessage('Missing camera stream URL')
            setResolution('Unavailable')
            return undefined
        }

        let closed = false
        let sessionUrl = ''
        let offerData: OfferData | null = null
        const queuedCandidates: RTCIceCandidate[] = []
        const pc = new RTCPeerConnection()

        const updateResolution = () => {
            setResolution(formatResolution(video.videoWidth, video.videoHeight))
            setVideoSize({
                width: video.videoWidth,
                height: video.videoHeight,
            })
        }

        const closeStream = () => {
            closed = true

            if (sessionUrl) {
                fetch(sessionUrl, { method: 'DELETE' }).catch(() => undefined)
            }

            pc.getSenders().forEach((sender) => {
                sender.track?.stop()
            })
            pc.getReceivers().forEach((receiver) => {
                receiver.track?.stop()
            })
            pc.close()

            video.pause()
            video.srcObject = null
        }

        const sendLocalCandidates = (candidates: RTCIceCandidate[]) => {
            if (!offerData || !sessionUrl || candidates.length === 0) {
                return
            }

            fetch(sessionUrl, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/trickle-ice-sdpfrag',
                    'If-Match': '*',
                },
                body: generateSdpFragment(offerData, candidates),
            }).catch(() => undefined)
        }

        const connect = async () => {
            setStatus('connecting')
            setErrorMessage('')
            setResolution('Detecting...')

            try {
                const optionsResponse = await fetch(endpointUrl, { method: 'OPTIONS' })
                const iceServers = parseIceServers(optionsResponse.headers.get('link'))

                if (iceServers.length > 0) {
                    pc.setConfiguration({ iceServers })
                }

                pc.addTransceiver('video', { direction: 'recvonly' })
                pc.addTransceiver('audio', { direction: 'recvonly' })
                pc.createDataChannel('')

                pc.ontrack = (event) => {
                    if (closed || !video.srcObject) {
                        video.srcObject = event.streams[0]
                    }
                }

                pc.onconnectionstatechange = () => {
                    if (closed) {
                        return
                    }

                    if (pc.connectionState === 'connected') {
                        setStatus('live')
                    }

                    if (['failed', 'disconnected', 'closed'].includes(pc.connectionState)) {
                        setStatus('error')
                        setErrorMessage(`WebRTC connection ${pc.connectionState}`)
                    }
                }

                pc.onicecandidate = (event) => {
                    if (!event.candidate) {
                        return
                    }

                    if (!sessionUrl) {
                        queuedCandidates.push(event.candidate)
                        return
                    }

                    sendLocalCandidates([event.candidate])
                }

                const offer = await pc.createOffer()
                offerData = parseOffer(offer.sdp ?? '')
                await pc.setLocalDescription(offer)

                const response = await fetch(endpointUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/sdp' },
                    body: offer.sdp,
                })

                if (!response.ok) {
                    throw new Error(`WHEP request failed with HTTP ${response.status}`)
                }

                sessionUrl = getSessionUrl(response, endpointUrl)
                const answer = await response.text()

                await pc.setRemoteDescription({
                    type: 'answer',
                    sdp: answer,
                })

                sendLocalCandidates(queuedCandidates.splice(0))

                if (!closed) {
                    await video.play()
                }
            } catch (error) {
                if (closed) {
                    return
                }

                setStatus('error')
                setResolution('Unavailable')
                setErrorMessage(error instanceof Error ? error.message : 'Unable to open camera stream')
            }
        }

        video.addEventListener('loadedmetadata', updateResolution)
        video.addEventListener('resize', updateResolution)
        connect()

        return () => {
            video.removeEventListener('loadedmetadata', updateResolution)
            video.removeEventListener('resize', updateResolution)
            closeStream()
        }
    }, [src, reconnectKey])

    return (
        <div
            ref={containerRef}
            className="relative min-h-[420px] overflow-hidden rounded-lg border border-slate-200 bg-slate-950 shadow-sm lg:min-h-[560px]"
        >
            <video
                ref={videoRef}
                autoPlay
                muted
                playsInline
                className="absolute inset-0 h-full w-full bg-slate-950 object-contain"
            />

            <canvas
                ref={detectionCanvasRef}
                className="pointer-events-none absolute inset-0 z-[1] h-full w-full"
            />

            <canvas
                ref={overlayCanvasRef}
                className="pointer-events-none absolute inset-0 z-[2] h-full w-full"
            />

            {status !== 'live' ? (
                <div className="absolute inset-0 z-[4] grid place-items-center bg-slate-950/80 px-6 text-center">
                    <div>
                        <div className="mx-auto mb-4 grid size-14 place-items-center rounded-full bg-white/10 text-xl font-bold text-white">
                            {status === 'connecting' ? '...' : '!'}
                        </div>
                        <p className="text-sm font-semibold text-white">
                            {status === 'connecting' ? 'Connecting to camera stream' : 'Unable to load camera stream'}
                        </p>
                        {errorMessage ? (
                            <p className="mt-2 max-w-md text-sm text-slate-300">{errorMessage}</p>
                        ) : null}
                    </div>
                </div>
            ) : null}

            <div className="absolute left-4 top-4 z-[3] rounded-lg border border-white/15 bg-slate-950/75 px-3 py-2 text-xs font-semibold text-white shadow-sm backdrop-blur">
                {resolution}
            </div>

            <div className="absolute right-4 top-4 z-[3] flex items-center gap-2 rounded-lg border border-white/15 bg-slate-950/75 px-3 py-2 text-xs font-semibold text-white shadow-sm backdrop-blur">
                <span
                    className={`size-2 rounded-full ${status === 'live'
                            ? 'bg-emerald-400'
                            : status === 'connecting'
                                ? 'bg-amber-400'
                                : 'bg-rose-400'
                        }`}
                />
                {status === 'live' ? 'Live' : status === 'connecting' ? 'Connecting' : 'Error'}
            </div>
        </div>
    )
}

export default CameraPreview
