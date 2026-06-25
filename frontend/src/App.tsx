import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { DashboardLayout } from "@/layouts/DashboardLayout"
import { DashboardPage } from "@/pages/DashboardPage"
import { CameraPage } from "@/pages/CameraPage"
import { UartPage } from "@/pages/UartPage"
import { ReidPage } from "@/pages/ReidPage"
import { ZoneStateMachinePage } from "@/pages/ZoneStateMachinePage"
import { DetectionPage } from "@/pages/DetectionPage"

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/cameras/:id" element={<CameraPage />} />
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
  )
}

export default App