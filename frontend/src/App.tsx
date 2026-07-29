import { lazy } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { ConfigGuard } from "@/components/config-guard"
import { DashboardLayout } from "@/layouts/DashboardLayout"

const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
)
const CameraPage = lazy(() =>
  import("@/pages/CameraPage").then((m) => ({ default: m.CameraPage })),
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

function App() {
  return (
    <ConfigGuard>
      <BrowserRouter>
        <Routes>
          <Route element={<DashboardLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/cameras/:id" element={<CameraPage />} />
            <Route
              path="/calibration/cameras/:id"
              element={<CameraCalibrationPage />}
            />
            <Route path="/uart" element={<UartPage />} />
            <Route path="/re-id" element={<ReidPage />} />
            <Route path="/zone-state-machine" element={<ZoneStateMachinePage />} />
            <Route path="/detection" element={<DetectionPage />} />
          </Route>
        </Routes>

        <Toaster
          richColors
          position="top-center"
          expand
          visibleToasts={3}
        />
      </BrowserRouter>
    </ConfigGuard>
  )
}

export default App
