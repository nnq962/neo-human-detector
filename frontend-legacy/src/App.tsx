import { ToastProvider } from './components/feedback/ToastProvider'
import Topbar from './components/layout/Topbar'
import GeneralConfig from './components/config/GeneralConfig'
import ZonesConfig from './components/config/ZonesConfig'

function AppContent() {
  return (
    <main className="min-h-screen bg-slate-50">
      <Topbar />
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <GeneralConfig />
        <ZonesConfig />
      </div>
    </main>
  )
}

function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  )
}

export default App
