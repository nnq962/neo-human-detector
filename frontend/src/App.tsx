import { lazy, Suspense } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { ConfigGuard } from "@/components/config-guard"
import { DashboardLayout } from "@/layouts/DashboardLayout"

const PublicCameraWallPage = lazy(() =>
  import("@/pages/PublicCameraWallPage").then((m) => ({
    default: m.PublicCameraWallPage,
  })),
)

const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
)
const CameraPageRoute = lazy(() =>
  import("@/pages/CameraPage").then((m) => ({ default: m.CameraPageRoute })),
)
const CameraCalibrationPage = lazy(() =>
  import("@/pages/CameraCalibrationPage").then((m) => ({
    default: m.CameraCalibrationPage,
  })),
)
const UartPage = lazy(() =>
  import("@/pages/UartPage").then((m) => ({ default: m.UartPage })),
)
const ReidPage = lazy(() =>
  import("@/pages/ReidPage").then((m) => ({ default: m.ReidPage })),
)
const ZoneStateMachinePage = lazy(() =>
  import("@/pages/ZoneStateMachinePage").then((m) => ({ default: m.ZoneStateMachinePage })),
)
const DetectionPage = lazy(() =>
  import("@/pages/DetectionPage").then((m) => ({ default: m.DetectionPage })),
)
const RobotDispatchPage = lazy(() =>
  import("@/pages/RobotDispatchPage").then((m) => ({ default: m.RobotDispatchPage })),
)
function App() {
  return (
    <BrowserRouter>
      <Suspense
        fallback={
          <div className="grid h-svh place-items-center bg-[#f7fbfc] text-sm text-cyan-800">
            Đang khởi tạo màn hình...
          </div>
        }
      >
        <Routes>
          <Route path="/live" element={<PublicCameraWallPage />} />
          <Route
            element={
              <ConfigGuard>
                <DashboardLayout />
              </ConfigGuard>
            }
          >
            <Route path="/" element={<DashboardPage />} />
            <Route path="/cameras/:id" element={<CameraPageRoute />} />
            <Route
              path="/calibration/cameras/:id"
              element={<CameraCalibrationPage />}
            />
            <Route path="/uart" element={<UartPage />} />
            <Route path="/re-id" element={<ReidPage />} />
            <Route path="/robot-dispatch" element={<RobotDispatchPage />} />
            <Route path="/zone-state-machine" element={<ZoneStateMachinePage />} />
            <Route path="/detection" element={<DetectionPage />} />
          </Route>
        </Routes>
      </Suspense>

      <Toaster
        richColors
        position="top-center"
        expand
        visibleToasts={3}
      />
    </BrowserRouter>
  )
}

export default App
