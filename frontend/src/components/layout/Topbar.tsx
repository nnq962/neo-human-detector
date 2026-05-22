import { useEffect, useState } from 'react'
import {
  getDetectorStatus,
  restartDetector,
  startDetector,
  stopDetector,
} from '../../api/detectorApi'
import { useToast } from '../../hooks/useToast'
import {
  clearRestartRequired,
  getRestartRequired,
  subscribeRestartRequiredChanged,
} from '../../lib/restartRequiredEvents'

const controlButtons = [
  {
    label: 'Start',
    icon: '▶',
    className:
      'border-emerald-200 bg-emerald-50 text-emerald-700 shadow-emerald-900/10 hover:border-emerald-300 hover:bg-emerald-100 hover:text-emerald-800 focus-visible:ring-emerald-500',
  },
  {
    label: 'Stop',
    icon: '■',
    className:
      'border-rose-200 bg-rose-50 text-rose-700 shadow-rose-900/10 hover:border-rose-300 hover:bg-rose-100 hover:text-rose-800 focus-visible:ring-rose-500',
  },
  {
    label: 'Restart',
    icon: '↻',
    className:
      'border-sky-200 bg-sky-50 text-sky-700 shadow-sky-900/10 hover:border-sky-300 hover:bg-sky-100 hover:text-sky-800 focus-visible:ring-sky-500',
  },
]

type DetectorRunStatus = 'loading' | 'running' | 'stopped' | 'error'
type DetectorAction = 'Start' | 'Stop' | 'Restart'

function Topbar() {
  const [detectorStatus, setDetectorStatus] = useState<DetectorRunStatus>('loading')
  const [pendingDetectorAction, setPendingDetectorAction] = useState<DetectorAction | null>(null)
  const [isRestartRequired, setIsRestartRequired] = useState(false)
  const toast = useToast()

  const baseButtonClass =
    'group inline-flex h-11 w-11 items-center justify-center gap-2 rounded-lg border px-0 text-sm font-semibold shadow-sm transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-white sm:w-auto sm:min-w-28 sm:px-4'

  useEffect(() => {
    let ignore = false

    const loadDetectorStatus = async () => {
      try {
        const status = await getDetectorStatus()

        if (!ignore) {
          setDetectorStatus(status.is_running ? 'running' : 'stopped')
        }
      } catch {
        if (!ignore) {
          setDetectorStatus('error')
        }
      }
    }

    loadDetectorStatus()
    const intervalId = window.setInterval(loadDetectorStatus, 10_000)

    return () => {
      ignore = true
      window.clearInterval(intervalId)
    }
  }, [])

  useEffect(() => {
    setIsRestartRequired(getRestartRequired())

    return subscribeRestartRequiredChanged(() => {
      setIsRestartRequired(getRestartRequired())
    })
  }, [])

  const refreshDetectorStatus = async () => {
    try {
      const status = await getDetectorStatus()
      setDetectorStatus(status.is_running ? 'running' : 'stopped')
    } catch {
      setDetectorStatus('error')
    }
  }

  const runDetectorAction = async (action: DetectorAction) => {
    setPendingDetectorAction(action)

    try {
      let message = ''

      if (action === 'Start') {
        const response = await startDetector()
        message = response.message
      }

      if (action === 'Stop') {
        const response = await stopDetector()
        message = response.message
      }

      if (action === 'Restart') {
        const response = await restartDetector()
        message = response.message
      }

      await refreshDetectorStatus()
      if (action === 'Start' || action === 'Restart') {
        clearRestartRequired()
      }
      toast.success(message || `${action} command completed.`)
    } catch {
      setDetectorStatus('error')
      toast.error(`${action} command failed.`)
    } finally {
      setPendingDetectorAction(null)
    }
  }

  const detectorStatusLabel =
    detectorStatus === 'loading'
      ? 'Checking'
      : detectorStatus === 'running'
        ? 'Running'
        : detectorStatus === 'stopped'
          ? 'Stopped'
          : 'Status error'

  const detectorDotClass =
    detectorStatus === 'running'
      ? 'bg-emerald-500'
      : detectorStatus === 'stopped'
        ? 'bg-amber-400'
        : detectorStatus === 'error'
          ? 'bg-rose-500'
          : 'bg-slate-300'

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 shadow-[0_12px_36px_rgba(15,23,42,0.08)] backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1600px] items-center justify-center gap-4 px-4 py-4 sm:px-6 lg:justify-between lg:px-8">
        <div className="hidden min-w-0 flex-1 lg:block">
          <h1 className="text-xl font-bold tracking-normal text-slate-950 sm:text-2xl">
            Configuration Panel
          </h1>
        </div>

        <div className="flex w-full items-center justify-center gap-2 sm:flex-row sm:flex-wrap sm:gap-3 lg:w-auto lg:justify-end">
          <div className="flex items-center gap-2 sm:gap-2">
            {isRestartRequired ? (
              <span
                title="Restart detector to apply saved changes"
                className="inline-flex h-11 w-11 items-center justify-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-0 text-xs font-semibold text-amber-700 shadow-sm sm:w-auto sm:min-w-36 sm:px-4"
              >
                <span className="grid size-5 place-items-center rounded-full bg-white/80 text-[12px] leading-none shadow-sm">
                  !
                </span>
                <span className="hidden sm:inline">Restart required</span>
              </span>
            ) : null}

            <span className="group inline-flex h-11 w-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-0 text-xs font-semibold text-slate-600 shadow-sm transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 hover:shadow-md active:translate-y-0 active:scale-[0.98] sm:w-auto sm:min-w-28 sm:px-4">
              <span className="relative grid size-5 place-items-center rounded-full bg-slate-50 shadow-sm transition-colors group-hover:bg-white">
                <span className={`absolute size-2 rounded-full ${detectorDotClass} opacity-75 animate-ping`} />
                <span className={`relative size-2 rounded-full ${detectorDotClass}`} />
              </span>
              <span className="hidden sm:inline">{detectorStatusLabel}</span>
            </span>

            {controlButtons.map((button) => (
              <button
                key={button.label}
                type="button"
                aria-label={button.label}
                onClick={() => runDetectorAction(button.label as DetectorAction)}
                disabled={pendingDetectorAction !== null}
                className={`${baseButtonClass} ${button.className}`}
              >
                <span className="grid size-5 place-items-center rounded-full bg-white/80 text-[11px] leading-none shadow-sm transition-colors group-hover:bg-white">
                  {button.icon}
                </span>
                <span className="hidden sm:inline">
                  {pendingDetectorAction === button.label ? 'Working...' : button.label}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </header>
  )
}

export default Topbar
