import { useCallback, useState } from 'react'
import { updateConfig } from './api/configApi'
import { ToastProvider } from './components/feedback/ToastProvider'
import Topbar from './components/layout/Topbar'
import GeneralConfig from './components/config/GeneralConfig'
import ZonesConfig from './components/config/ZonesConfig'
import { useToast } from './hooks/useToast'
import type { AppConfig, Zone } from './types/config'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

function AppContent() {
  const [generalConfig, setGeneralConfig] = useState<Omit<AppConfig, 'zones'> | null>(null)
  const [zones, setZones] = useState<Zone[] | null>(null)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [configReloadKey, setConfigReloadKey] = useState(0)
  const toast = useToast()

  const saveConfig = useCallback(async () => {
    if (!generalConfig || !zones) {
      return
    }

    setSaveStatus('saving')

    try {
      await updateConfig({
        ...generalConfig,
        zones,
      })
      setConfigReloadKey((current) => current + 1)
      setSaveStatus('saved')
      toast.success('Config saved successfully.')
      window.setTimeout(() => setSaveStatus('idle'), 1600)
    } catch {
      setSaveStatus('error')
      toast.error('Failed to save config.')
    }
  }, [generalConfig, toast, zones])

  return (
    <main className="min-h-screen bg-slate-50">
      <Topbar
        onSaveConfig={saveConfig}
        saveStatus={saveStatus}
        canSave={generalConfig !== null && zones !== null}
      />
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <GeneralConfig reloadKey={configReloadKey} onConfigChange={setGeneralConfig} />
        <ZonesConfig reloadKey={configReloadKey} onZonesChange={setZones} />
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
