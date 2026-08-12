import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react"
import {
  CalendarDays,
  Radio,
  Settings,
  ShieldCheck,
  Users,
  Video,
} from "lucide-react"

import neoMiniLogo from "@/assets/neo-mini.svg"
import robotImage from "@/assets/H2.png"
import { CameraPreview } from "@/components/camera-preview"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Switch } from "@/components/ui/switch"
import { useCameras, type Camera as CameraModel } from "@/hooks/use-cameras"
import {
  subscribeBboxes,
  type RuntimeZonePayload,
} from "@/lib/bbox-stream"
import { cn } from "@/lib/utils"

const DESIGN_WIDTH = 1920
const DESIGN_HEIGHT = 1080
const CAMERA_SELECTION_KEY = "neo-public-camera-wall-selection"
const MAX_VISIBLE_CAMERAS = 4

const MOCK_ROBOT_ROWS = [
  // ===== THÔNG TIN CHUNG =====
  ["Thương hiệu", "UBTECH"],
  ["Tên sản phẩm", "CADEBOT L100"],
  ["Model", "XCAD101"],
  ["Loại robot", "Robot giao hàng / phục vụ thông minh"],
  ["Ứng dụng", "Nhà hàng, khách sạn, siêu thị, bán lẻ, sân bay, nhà máy"],
  ["Môi trường sử dụng", "Trong nhà"],

  // ===== KÍCH THƯỚC & TRỌNG LƯỢNG =====
  ["Kích thước (D × R × C)", "551 × 484 × 1252 mm"],
  ["Chiều dài", "551 mm"],
  ["Chiều rộng", "484 mm"],
  ["Chiều cao", "1252 mm"],
  ["Trọng lượng robot", "55 kg"],

  // ===== KHẢ NĂNG VẬN CHUYỂN =====
  ["Tổng tải trọng", "40 kg"],
  ["Số lượng khay", "4 khay"],
  ["Tải trọng tối đa mỗi khay", "10 kg"],
  ["Cảm biến khay", "Cảm biến hồng ngoại"],
  ["Nhận biết lấy đồ", "Có"],
  ["Đèn hướng dẫn lấy đồ", "Có"],

  // ===== KHẢ NĂNG DI CHUYỂN =====
  ["Tốc độ di chuyển", "0 – 0.8 m/s"],
  ["Chiều rộng lối đi tối thiểu", "Khoảng 650 mm"],
  ["Khả năng leo dốc", "≤ 5°"],
  ["Khả năng vượt vật cản", "≤ 20 mm"],
  ["Khả năng vượt rãnh", "≤ 40 mm"],
  ["Hệ thống treo", "Hệ thống treo độc lập thích ứng mặt sàn"],
  ["Giảm xóc", "Có"],
  ["Tự động giảm tốc khi xuống/lên dốc", "Có"],

  // ===== PIN =====
  ["Loại pin", "Pin sạc tích hợp"],
  ["Điện áp pin", "25.41 V"],
  ["Dung lượng pin", "20 Ah"],
  ["Thời gian hoạt động", "Khoảng 8 giờ"],
  ["Thời gian chờ", "Khoảng 12 giờ"],
  ["Thời gian sạc", "Khoảng 4 giờ"],
  ["Tự động quay về sạc", "Có"],
  ["Vừa sạc vừa hoạt động", "Có"],

  // ===== HỆ THỐNG SẠC =====
  ["Phương pháp sạc", "Adapter hoặc trạm sạc"],
  ["Điện áp đầu vào bộ sạc", "AC 100 – 240 V"],
  ["Điện áp đầu ra bộ sạc", "DC 29.4 V"],
  ["Trạm sạc tự động", "Hỗ trợ"],
  ["Tự động docking", "Có"],

  // ===== MÀN HÌNH =====
  ["Màn hình điều khiển", "10.1 inch"],
  ["Độ phân giải màn hình điều khiển", "1920 × 1200"],
  ["Màn hình quảng cáo", "21.5 inch"],
  ["Độ phân giải màn hình quảng cáo", "1920 × 1080"],
  ["Tỷ lệ màn hình quảng cáo", "16:9"],
  ["Hiển thị quảng cáo", "Có"],
  ["Quản lý nội dung quảng cáo", "USB / nền tảng quản lý cloud"],

  // ===== WIFI & KẾT NỐI =====
  ["Wi-Fi", "2.4 GHz / 5 GHz"],
  ["Mạng di động", "Hỗ trợ 4G / LTE"],
  ["LoRa", "Có"],
  ["Giao tiếp nhiều robot", "Có"],
  ["Hoạt động phối hợp nhiều robot", "Có"],
  ["Đồng bộ bản đồ giữa nhiều robot", "Có"],

  // ===== ĐỊNH VỊ & DẪN ĐƯỜNG =====
  ["Công nghệ định vị", "U-SLAM"],
  ["SLAM", "Laser SLAM + Visual SLAM"],
  ["Tự động lập bản đồ", "Có"],
  ["Chỉnh sửa bản đồ", "Có"],
  ["Chỉnh sửa bản đồ từ xa", "Có"],
  ["Tự động lập kế hoạch đường đi", "Có"],
  ["Tự động chọn đường tối ưu", "Có"],
  ["Điều hướng tự động", "Có"],
  ["Chia sẻ bản đồ nhiều robot", "Có"],

  // ===== CẢM BIẾN & TRÁNH VẬT CẢN =====
  ["LiDAR", "Có, phía trước và phía sau"],
  ["Camera độ sâu RGB-D", "Có"],
  ["Cảm biến siêu âm", "Có"],
  ["Cảm biến hồng ngoại", "Có"],
  ["Tránh vật cản 3D", "Có"],
  ["Phát hiện vách kính", "Có"],
  ["Tránh vật cản kính", "Có"],
  ["Phát hiện mép / cầu thang", "Có"],
  ["Chống rơi", "Có"],
  ["Tự động tránh vật cản", "Có"],

  // ===== ÂM THANH & TƯƠNG TÁC =====
  ["Loa", "1 loa tích hợp"],
  ["Microphone", "Mảng 6 microphone"],
  ["Phạm vi nhận diện giọng nói", "Lên đến khoảng 5 m"],
  ["Góc thu âm", "360°"],
  ["Nhận diện giọng nói", "Có"],
  ["NLP", "Có"],
  ["TTS", "Có"],
  ["Phát giọng nói tùy chỉnh", "Có"],
  ["Biểu cảm hoạt hình", "Có"],
  ["Tương tác ánh sáng", "Có"],
  ["Tương tác cảm ứng thân robot", "Có"],
  ["Theo dõi ánh mắt / người dùng", "Có"],

  // ===== CHẾ ĐỘ HOẠT ĐỘNG =====
  ["Chế độ giao hàng", "Có"],
  ["Giao hàng nhiều bàn", "Có"],
  ["Chế độ chào đón khách", "Có"],
  ["Chế độ dẫn khách", "Có"],
  ["Chế độ tuần tra", "Có"],
  ["Chế độ quảng cáo", "Có"],
  ["Chế độ sinh nhật", "Có"],
  ["Tự động phát thông báo", "Có"],

  // ===== BẢO MẬT & PHÂN QUYỀN =====
  ["Nhận diện khuôn mặt", "Có"],
  ["Xác thực bằng mật khẩu", "Có"],
  ["Phân quyền vận hành", "Có"],

  // ===== PHẦN MỀM QUẢN LÝ =====
  ["Nền tảng quản lý", "CARS"],
  ["Tên đầy đủ", "Cadebot Artificial Intelligence Robot System"],
  ["Quản lý trạng thái robot", "Có"],
  ["Quản lý bản đồ", "Có"],
  ["Quản lý nội dung quảng cáo", "Có"],
  ["Quản lý nhiều robot", "Có"],
  ["Quản lý từ xa", "Có"],
  ["Triển khai cloud", "Có"],
  ["Triển khai private / on-premise", "Hỗ trợ tùy cấu hình"],

  // ===== ĐIỀU KIỆN HOẠT ĐỘNG =====
  ["Nhiệt độ hoạt động", "0 – 40°C"],
  ["Độ ẩm hoạt động", "10 – 90%"],
  ["Nhiệt độ lưu trữ", "-20 – 60°C"],
  ["Vị trí sử dụng", "Trong nhà"],

  // ===== PHỤ KIỆN =====
  ["Nắp chống bụi", "Hỗ trợ tùy chọn"],
  ["Giá để rượu", "Hỗ trợ tùy chọn"],
  ["Giá để cốc", "Hỗ trợ tùy chọn"],
  ["Hộp thu hồi khay / đĩa", "Hỗ trợ tùy chọn"],
  ["Bộ gọi vật lý", "Hỗ trợ tùy chọn"],

  // ===== TÍNH NĂNG KHÁC =====
  ["Tùy chỉnh giao diện robot", "Có"],
  ["Tùy chỉnh skin thân robot", "Hỗ trợ"],
  ["Tùy chỉnh nội dung quảng cáo", "Có"],
  ["Nhập quảng cáo bằng USB", "Có"],
  ["Quản lý quảng cáo qua cloud", "Có"],
  ["Hỗ trợ OTA", "Có"],
];

const ROBOT_INFO_ROW_HEIGHT = 23
const ROBOT_INFO_ROW_GAP = 20
const ROBOT_INFO_LIST_HEIGHT =
  MOCK_ROBOT_ROWS.length * ROBOT_INFO_ROW_HEIGHT
  + (MOCK_ROBOT_ROWS.length - 1) * ROBOT_INFO_ROW_GAP
const ROBOT_INFO_SCROLL_DISTANCE =
  ROBOT_INFO_LIST_HEIGHT + ROBOT_INFO_ROW_GAP
const ROBOT_INFO_ANIMATION_STYLE = {
  "--robot-info-scroll-distance": `-${ROBOT_INFO_SCROLL_DISTANCE}px`,
  animationDuration: `${Math.max(14, MOCK_ROBOT_ROWS.length * 2)}s`,
} as CSSProperties

interface RuntimeCameraSummary {
  detectionCount: number
  zones: RuntimeZonePayload[]
}

const SIDE_PANEL_STYLE: CSSProperties = {
  background: "rgba(240, 240, 240, 0.3)",
  boxShadow: [
    "-2px 4px 10px 0 rgba(145, 145, 145, 0.05)",
    "-7px 17px 18px 0 rgba(145, 145, 145, 0.04)",
    "-15px 37px 24px 0 rgba(145, 145, 145, 0.03)",
    "-27px 66px 29px 0 rgba(145, 145, 145, 0.01)",
    "-42px 103px 31px 0 rgba(145, 145, 145, 0)",
  ].join(", "),
}

const SIDE_PANEL_BORDER_STYLE: CSSProperties = {
  background:
    "conic-gradient(from 102.21deg at 52.75% 38.75%, rgba(249, 249, 249, 0.5) -32.95deg, rgba(64, 64, 64, 0.5) 10.52deg, rgba(64, 64, 64, 0.35) 32.12deg, rgba(255, 255, 255, 0.5) 60.28deg, rgba(255, 255, 255, 0.5) 107.79deg, rgba(64, 64, 64, 0.35) 187.59deg, #f9f9f9 207.58deg, rgba(255, 255, 255, 0.5) 287.31deg, rgba(249, 249, 249, 0.5) 327.05deg, rgba(64, 64, 64, 0.5) 370.52deg)",
  WebkitMask:
    "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
  WebkitMaskComposite: "xor",
  maskComposite: "exclude",
}

const LIVE_BADGE_STYLE: CSSProperties = {
  background: "linear-gradient(180deg, #00c951 0%, #00a63e 100%)",
  boxShadow: [
    "0 24.72px 32.26px 0 rgba(0, 229, 141, 0.19)",
    "0 42px 107px 0 rgba(0, 229, 141, 0.34)",
  ].join(", "),
}

const LIVE_BADGE_BORDER_STYLE: CSSProperties = {
  background:
    "linear-gradient(180deg, rgba(0, 166, 62, 0.55) 0%, rgba(0, 201, 81, 0.55) 100%)",
  WebkitMask:
    "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
  WebkitMaskComposite: "xor",
  maskComposite: "exclude",
}

function getCanvasScale() {
  if (typeof window === "undefined") return 1
  return Math.min(
    window.innerWidth / DESIGN_WIDTH,
    window.innerHeight / DESIGN_HEIGHT,
  )
}

function readSavedSelection(): string[] | null {
  try {
    const value = localStorage.getItem(CAMERA_SELECTION_KEY)
    if (value === null) return null
    const parsed = JSON.parse(value)
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string")
      : null
  } catch {
    return null
  }
}

function runtimeSummariesEqual(
  current: Record<string, RuntimeCameraSummary>,
  next: Record<string, RuntimeCameraSummary>,
) {
  const currentCameraIds = Object.keys(current)
  const nextCameraIds = Object.keys(next)
  return currentCameraIds.length === nextCameraIds.length
    && nextCameraIds.every((cameraId) => {
      const currentSummary = current[cameraId]
      const nextSummary = next[cameraId]
      if (!currentSummary || !nextSummary) return false
      return currentSummary.detectionCount === nextSummary.detectionCount
        && currentSummary.zones.length === nextSummary.zones.length
        && nextSummary.zones.every((zone, index) => {
          const currentZone = currentSummary.zones[index]
          return currentZone?.id === zone.id
            && currentZone.name === zone.name
            && currentZone.state === zone.state
        })
    })
}

function getZoneStatusPresentation(state: string) {
  switch (state) {
    case "PENDING_ENTER":
      return {
        label: "Đang vào",
        dotClassName: "bg-amber-300",
        rowClassName: "border-l-2 border-l-amber-300 bg-amber-300/8",
      }
    case "OCCUPIED":
      return {
        label: "Có người",
        dotClassName: "bg-emerald-400",
        rowClassName: "border-l-2 border-l-white bg-white/5",
      }
    case "PENDING_EXIT":
      return {
        label: "Đang rời",
        dotClassName: "bg-orange-300",
        rowClassName: "border-l-2 border-l-orange-300 bg-orange-300/8",
      }
    case "EMPTY":
      return {
        label: "Trống",
        dotClassName: "bg-white",
        rowClassName: "",
      }
    default:
      return {
        label: state,
        dotClassName: "bg-slate-300",
        rowClassName: "",
      }
  }
}

function formatDateTime(date: Date) {
  const datePart = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date).replaceAll("/", "-")
  const weekdayPart = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
  }).format(date)
  const timePart = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date)

  return { datePart, weekdayPart, timePart }
}

function MetricCard({
  icon,
  iconClassName,
  label,
  value,
}: {
  icon: ReactNode
  iconClassName: string
  label: string
  value: string
}) {
  return (
    <article className="flex h-[121px] min-w-0 items-center gap-[30px] rounded-[20px] border border-white/10 bg-white/30 p-[20px] shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] backdrop-blur-[70px]">
      <div
        className={cn(
          "grid h-[56px] w-[56px] shrink-0 place-items-center rounded-lg border border-black/5 px-[12px] py-[8px]",
          iconClassName,
        )}
      >
        {icon}
      </div>
      <div className="flex h-[81px] w-[303.33331298828125px] min-w-0 flex-col gap-[12px] font-['Space_Grotesk_Variable']">
        <p className="flex h-[23px] items-center truncate text-[18px] leading-none font-medium tracking-normal text-white">
          {label}
        </p>
        <p className="flex h-[46px] items-center text-[36px] leading-none font-bold tracking-normal text-white">
          {value}
        </p>
      </div>
    </article>
  )
}

function CameraSettingsSheet({
  cameras,
  selectedIds,
  onSelectionChange,
}: {
  cameras: CameraModel[]
  selectedIds: string[]
  onSelectionChange: (cameraIds: string[]) => void
}) {
  const enabledCameras = cameras.filter((camera) => camera.enabled)
  const selectedCameraIds = enabledCameras
    .filter((camera) => selectedIds.includes(camera.id))
    .map((camera) => camera.id)
  const selectedCount = selectedCameraIds.length
  const selectableCameraCount = Math.min(
    enabledCameras.length,
    MAX_VISIBLE_CAMERAS,
  )

  const toggleCamera = (cameraId: string, checked: boolean) => {
    if (checked && selectedCount >= MAX_VISIBLE_CAMERAS) return
    const nextIds = checked
      ? [...new Set([...selectedCameraIds, cameraId])]
      : selectedCameraIds.filter((id) => id !== cameraId)
    onSelectionChange(nextIds)
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <button
          type="button"
          aria-label="Mở cài đặt camera"
          className="grid size-[42px] place-items-center rounded-full bg-[#f47731] text-white shadow-[0_8px_24px_rgba(244,119,49,0.28)] transition hover:bg-[#ff8640] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
        >
          <Settings className="size-5" />
        </button>
      </SheetTrigger>

      <SheetContent className="!w-[680px] !max-w-[min(680px,100vw)] gap-0 overflow-x-hidden border-l border-slate-200 bg-white p-0 text-slate-950">
        <SheetHeader className="gap-4 px-9 pt-12 pb-8 text-left">
          <SheetTitle className="font-['Space_Grotesk_Variable'] text-[34px] leading-none font-medium text-slate-950">
            Camera trình chiếu
          </SheetTitle>
          <SheetDescription className="max-w-[610px] text-[18px] leading-8 text-slate-500">
            Chọn các luồng được phép xuất hiện trên màn hình dành cho khách.
            <br />
            Thiết lập được lưu trên trình duyệt này.
          </SheetDescription>
          <div className="mt-2 h-px bg-slate-200" />
        </SheetHeader>

        <div className="mx-9 flex h-[82px] shrink-0 items-center rounded-full bg-slate-100 px-7">
          <div className="flex min-w-0 flex-1 items-center gap-5 text-[20px] font-semibold">
            <Video className="size-6" />
            <span>
              {selectedCount}/{selectableCameraCount} đang hiển thị
            </span>
          </div>
          <div className="h-7 w-px bg-slate-200" />
          <div className="flex items-center gap-1 pl-6">
            <Button
              variant="ghost"
              className="h-11 px-4 text-[18px] font-semibold hover:bg-white/70"
              onClick={() =>
                onSelectionChange(
                  enabledCameras
                    .slice(0, MAX_VISIBLE_CAMERAS)
                    .map((camera) => camera.id),
                )
              }
            >
              Chọn tất cả
            </Button>
            <Button
              variant="ghost"
              className="h-11 px-4 text-[18px] font-semibold hover:bg-white/70"
              onClick={() => onSelectionChange([])}
            >
              Bỏ chọn
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-9 py-9">
          {cameras.map((camera, index) => {
            const checked = camera.enabled && selectedIds.includes(camera.id)
            return (
              <div
                key={camera.id}
                className={cn(
                  "flex min-h-[144px] items-center gap-5 rounded-[30px] border border-slate-200 bg-slate-50 px-9 py-6",
                  !camera.enabled && "opacity-50",
                )}
              >
                <div className="grid size-[68px] shrink-0 place-items-center rounded-2xl bg-white text-[27px] font-medium shadow-sm">
                  {String(index + 1).padStart(2, "0")}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[25px] leading-none font-semibold">
                    {camera.name}
                  </p>
                  <p className="mt-3 flex items-center gap-2 text-[18px] leading-none text-slate-500">
                    <span
                      className={cn(
                        "size-2.5 rounded-full",
                        camera.enabled ? "bg-emerald-400" : "bg-slate-400",
                      )}
                    />
                    {camera.enabled ? "Sẵn sàng trình chiếu" : "Camera đang tắt"}
                  </p>
                </div>
                <Switch
                  checked={checked}
                  disabled={
                    !camera.enabled
                    || (!checked && selectedCount >= MAX_VISIBLE_CAMERAS)
                  }
                  aria-label={`Hiển thị ${camera.name}`}
                  className="data-checked:border-emerald-400 data-checked:bg-emerald-400 data-checked:drop-shadow-[0_2px_0_#25a978]"
                  onCheckedChange={(value) => toggleCamera(camera.id, value)}
                />
              </div>
            )
          })}

          {cameras.length === 0 && (
            <div className="rounded-[30px] border border-dashed border-slate-300 bg-slate-50 px-6 py-16 text-center text-[18px] text-slate-500">
              Chưa có camera trong hệ thống.
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

export function PublicCameraWallPage() {
  const { data: cameras = [], isLoading, isError } = useCameras()
  const [now, setNow] = useState(() => new Date())
  const [canvasScale, setCanvasScale] = useState(getCanvasScale)
  const [selectedIds, setSelectedIds] = useState<string[] | null>(
    readSavedSelection,
  )
  const [runtimeSummaries, setRuntimeSummaries] = useState<
    Record<string, RuntimeCameraSummary>
  >({})
  const [cameraStreamActive, setCameraStreamActive] = useState<
    Record<string, boolean>
  >({})
  const formattedDateTime = formatDateTime(now)

  const enabledCameras = useMemo(
    () => cameras.filter((camera) => camera.enabled),
    [cameras],
  )
  const effectiveSelectedIds = (
    selectedIds
    ?? enabledCameras
      .slice(0, MAX_VISIBLE_CAMERAS)
      .map((camera) => camera.id)
  ).slice(0, MAX_VISIBLE_CAMERAS)
  const visibleCameras = enabledCameras.filter((camera) =>
    effectiveSelectedIds.includes(camera.id)
  ).slice(0, MAX_VISIBLE_CAMERAS)
  const activeCamera = visibleCameras[0] ?? null
  const activeCameraCount = visibleCameras.filter(
    (camera) => cameraStreamActive[camera.id] === true,
  ).length
  const detectedPersonCount = visibleCameras.reduce(
    (total, camera) =>
      total + (runtimeSummaries[camera.id]?.detectionCount ?? 0),
    0,
  )
  const activeCameraSummary = activeCamera
    ? runtimeSummaries[activeCamera.id]
    : undefined
  const monitoredZones = activeCameraSummary?.zones
    ?? activeCamera?.zones.map((zone) => ({
      id: zone.id ?? null,
      name: zone.name,
      state: "EMPTY",
    }))
    ?? []
  const zoneListHeight = monitoredZones.length * 53
    + Math.max(0, monitoredZones.length - 1) * 4
  const zoneAnimationStyle = {
    "--zone-info-scroll-distance": `-${zoneListHeight + 4}px`,
    animationDuration: `${Math.max(8, monitoredZones.length * 3)}s`,
  } as CSSProperties

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const updateSelection = (cameraIds: string[]) => {
    const limitedCameraIds = cameraIds.slice(0, MAX_VISIBLE_CAMERAS)
    setSelectedIds(limitedCameraIds)
    localStorage.setItem(
      CAMERA_SELECTION_KEY,
      JSON.stringify(limitedCameraIds),
    )
  }

  useEffect(() => {
    const updateCanvasScale = () => setCanvasScale(getCanvasScale())
    window.addEventListener("resize", updateCanvasScale)
    return () => window.removeEventListener("resize", updateCanvasScale)
  }, [])

  useEffect(() => subscribeBboxes((batch) => {
    const nextSummaries = batch
      ? Object.fromEntries(
          Object.entries(batch.cameras).map(([cameraId, payload]) => [
            cameraId,
            {
              detectionCount: payload.detections.length,
              zones: Object.values(payload.zones),
            },
          ]),
        )
      : {}
    setRuntimeSummaries((current) =>
      runtimeSummariesEqual(current, nextSummaries) ? current : nextSummaries
    )
  }), [])

  const updateCameraStreamActive = useCallback(
    (cameraId: string, active: boolean) => {
      setCameraStreamActive((current) => {
        if (current[cameraId] === active) return current
        return { ...current, [cameraId]: active }
      })
    },
    [],
  )

  return (
    <main
      className="relative flex h-svh w-full items-center justify-center overflow-hidden bg-[#0d1212]"
      style={{
        background: [
          "radial-gradient(circle at 18% 24%, rgba(120, 107, 16, 0.48), transparent 35%)",
          "radial-gradient(circle at 87% 13%, rgba(56, 122, 151, 0.52), transparent 37%)",
          "radial-gradient(circle at 72% 91%, rgba(144, 76, 42, 0.5), transparent 42%)",
          "linear-gradient(113deg, #1e2315 0%, #101918 47%, #15232a 72%, #1d292b 100%)",
        ].join(", "),
      }}
    >
      <div className="pointer-events-none absolute inset-0 bg-black/10 backdrop-blur-[1px]" />
      <div
        className="relative h-[1080px] w-[1920px] shrink-0 overflow-hidden text-white"
        style={{ transform: `scale(${canvasScale})` }}
      >
        <div className="relative z-10 flex h-full flex-col px-[30px] pt-[30px] pb-[30px]">
        <header
          className="flex h-[73px] w-full shrink-0 items-center justify-between px-[30px] py-[15px]"
        >
          <div className="flex items-center gap-5">
            <img
              src={neoMiniLogo}
              alt="NEO Robotics"
              className="h-[36px] w-[35px] object-contain"
            />
            <h1 className="flex h-[43px] w-[415px] items-center font-['Space_Grotesk_Variable'] text-[34px] leading-none font-medium tracking-normal text-white">
              NEO ROBOTICS AI CAMERA
            </h1>
          </div>

          <div className="flex items-center gap-7">
            <div className="flex items-center gap-3 text-white">
              <CalendarDays className="size-5" />
              <div className="flex items-center gap-7 font-['Space_Grotesk_Variable'] text-[16px] leading-none font-medium tracking-normal tabular-nums">
                <span className="flex h-5 w-[92px] items-center whitespace-nowrap">
                  {formattedDateTime.datePart}
                </span>
                <span>{formattedDateTime.weekdayPart}</span>
                <span>{formattedDateTime.timePart}</span>
              </div>
            </div>
            <CameraSettingsSheet
              cameras={cameras}
              selectedIds={effectiveSelectedIds}
              onSelectionChange={updateSelection}
            />
          </div>
        </header>

        <div className="mt-[28px] grid h-[909px] min-h-0 shrink-0 grid-cols-[1328px_512px] gap-[20px]">
          <section className="grid min-h-0 grid-rows-[121px_751px] gap-[37px]">
            <div className="grid grid-cols-3 gap-[20px]">
              <MetricCard
                icon={<Radio className="size-7" strokeWidth={2.2} />}
                iconClassName="bg-[#f0fdf4] text-[#31c86a]"
                label="Camera hoạt động"
                value={String(activeCameraCount).padStart(2, "0")}
              />
              <MetricCard
                icon={<Users className="size-7" strokeWidth={2.2} />}
                iconClassName="bg-[#fff7ed] text-[#f47731]"
                label="Số người phát hiện"
                value={String(detectedPersonCount)}
              />
              <MetricCard
                icon={<ShieldCheck className="size-7" strokeWidth={2.2} />}
                iconClassName="bg-[#eff6ff] text-[#4285ff]"
                label="Trạng thái an ninh"
                value="TỐT"
              />
            </div>

            <div className="grid h-[751px] w-[1318px] grid-cols-2 grid-rows-2 gap-[10px]">
              {visibleCameras.length > 0 ? (
                visibleCameras.map((camera) => (
                  <article
                    key={camera.id}
                    className={cn(
                      "relative flex min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-[20px] border border-transparent backdrop-blur-[25px]",
                      visibleCameras.length === 1
                        ? "col-span-2 row-span-2 p-[10px]"
                        : "p-[6px]",
                    )}
                    style={SIDE_PANEL_STYLE}
                  >
                    <div
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-0 rounded-[20px] p-px"
                      style={SIDE_PANEL_BORDER_STYLE}
                    />
                    <div className="relative h-full max-w-full aspect-video overflow-hidden rounded-[14px] bg-black">
                        <CameraPreview
                          src={camera.webrtc_address ?? ""}
                          cameraId={camera.id}
                          zones={camera.zones}
                          bboxCameraId={camera.id}
                          hideFaceKeypoints
                          hideStreamBadges
                          videoBorderRadius={14}
                          onVideoSizeChange={(size) =>
                            updateCameraStreamActive(camera.id, size !== null)
                          }
                        />
                        <div
                          className="pointer-events-none absolute top-3 left-3 z-50 flex h-[38px] w-[122px] items-center justify-center gap-[10px] rounded-[100px] border border-transparent px-[12px] py-[8px] text-sm font-medium text-white"
                          style={LIVE_BADGE_STYLE}
                        >
                          <div
                            aria-hidden="true"
                            className="absolute inset-0 rounded-[100px] p-px"
                            style={LIVE_BADGE_BORDER_STYLE}
                          />
                          <span className="relative">Stream: LIVE</span>
                        </div>
                    </div>
                  </article>
                ))
              ) : (
                <div className="col-span-2 row-span-2 grid h-full place-items-center rounded-[20px] bg-black/55 text-base text-white/65">
                  {isLoading
                    ? "Đang kết nối camera..."
                    : isError
                      ? "Không thể tải danh sách camera"
                      : "Chưa có camera đang hoạt động"}
                </div>
              )}
            </div>
          </section>

          <aside className="grid h-[909px] min-h-0 grid-rows-[337px_552px] gap-[20px]">
            <section
              className="relative flex h-[337px] flex-col gap-[21px] overflow-hidden rounded-[20px] border border-transparent px-[30px] py-[20px] backdrop-blur-[25px]"
              style={SIDE_PANEL_STYLE}
            >
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 rounded-[20px] p-px"
                style={SIDE_PANEL_BORDER_STYLE}
              />
              <h2 className="flex h-[36px] w-[450px] items-center font-['Space_Grotesk_Variable'] text-[28px] leading-none font-medium tracking-normal">
                Giám sát
              </h2>

              <div className="flex h-[238px] w-[450px] flex-col gap-[34px]">
                <div className="flex h-[94px] w-[450px] shrink-0 flex-col gap-[5px] rounded-[20px] bg-black/20 px-[30px] py-[15px] backdrop-blur-[70px]">
                  <p className="text-[15px] font-medium text-white/85">
                    {(activeCamera?.name ?? "CAM_01").toUpperCase()} COUNT
                  </p>
                  <p className="text-[25px] leading-none font-medium">
                    {activeCameraSummary?.detectionCount ?? 0}
                  </p>
                </div>

                <div className="h-[110px] w-[450px] overflow-hidden">
                  {monitoredZones.length > 0 ? (
                    <div
                      className={cn(
                        "flex flex-col gap-[4px] hover:[animation-play-state:paused] motion-reduce:animate-none",
                        monitoredZones.length > 1
                        && "animate-[zone-info-scroll_1s_linear_infinite]",
                      )}
                      style={zoneAnimationStyle}
                    >
                      {(monitoredZones.length > 1
                        ? [false, true]
                        : [false]
                      ).map((isDuplicate) => (
                        <div
                          key={String(isDuplicate)}
                          aria-hidden={isDuplicate || undefined}
                          className="flex w-[450px] shrink-0 flex-col gap-[4px]"
                          style={{ height: zoneListHeight }}
                        >
                          {monitoredZones.map((zone, index) => {
                            const status = getZoneStatusPresentation(zone.state)
                            return (
                              <div
                                key={`${zone.id ?? zone.name}-${index}`}
                                className={cn(
                                  "flex h-[53px] w-[450px] shrink-0 items-center justify-between bg-[#617078]/45 px-4 text-[15px]",
                                  status.rowClassName,
                                )}
                              >
                                <span className="min-w-0 truncate font-medium">
                                  {zone.name}
                                </span>
                                <span className="flex shrink-0 items-center gap-2 pl-4">
                                  <span
                                    className={cn(
                                      "size-2 rounded-full",
                                      status.dotClassName,
                                    )}
                                  />
                                  {status.label}
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="grid h-full place-items-center bg-[#617078]/45 text-[15px] text-white/70">
                      Camera chưa cấu hình zone
                    </div>
                  )}
                </div>
              </div>
            </section>

            <section
              className="relative flex h-[552px] min-h-0 flex-col gap-[21px] overflow-hidden rounded-[20px] border border-transparent px-[30px] py-[20px] backdrop-blur-[25px]"
              style={SIDE_PANEL_STYLE}
            >
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 rounded-[20px] p-px"
                style={SIDE_PANEL_BORDER_STYLE}
              />
              <h2 className="flex h-[36px] w-[450px] items-center font-['Space_Grotesk_Variable'] text-[28px] leading-none font-medium tracking-normal">
                Thông tin robot
              </h2>

              <div className="flex h-[453px] w-[450px] flex-col gap-[30px]">
                <img
                  src={robotImage}
                  alt="Robot NEO Robotics"
                  className="mx-auto h-[185px] w-[300px] shrink-0 rounded-[20px] object-contain"
                />

                <div className="h-[238px] w-[450px] overflow-hidden">
                  <div
                    className="flex flex-col gap-[20px] animate-[robot-info-scroll_1s_linear_infinite] hover:[animation-play-state:paused] motion-reduce:animate-none"
                    style={ROBOT_INFO_ANIMATION_STYLE}
                  >
                    {[false, true].map((isDuplicate) => (
                      <dl
                        key={String(isDuplicate)}
                        aria-hidden={isDuplicate || undefined}
                        className="flex w-[450px] shrink-0 flex-col gap-[20px] font-['Space_Grotesk_Variable'] text-[18px] leading-none tracking-normal"
                        style={{ height: ROBOT_INFO_LIST_HEIGHT }}
                      >
                        {MOCK_ROBOT_ROWS.map(([label, value], index) => (
                          <div
                            key={`${label}-${index}`}
                            className="flex h-[23px] w-[450px] shrink-0 items-center justify-between gap-5"
                          >
                            <dt className="min-w-0 flex-1 truncate text-white">
                              {label}
                            </dt>
                            <dd className="max-w-[260px] shrink-0 truncate text-right text-white">
                              {value}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ))}
                  </div>
                </div>
              </div>
            </section>
          </aside>
          </div>
        </div>
      </div>
    </main>
  )
}
