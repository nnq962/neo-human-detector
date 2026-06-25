import AIConfig from './general/AIConfig'
import CameraConfig from './general/CameraConfig'
import UartConfig from './general/UartConfig'
import ZoneStateMachineConfig from './general/ZoneStateMachineConfig'

const inputClass =
    'h-11 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 hover:border-slate-300 focus:border-sky-400 focus:ring-2 focus:ring-sky-100'

const labelClass = 'text-sm font-semibold text-slate-700'

function GeneralConfig() {
    return (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_12px_36px_rgba(15,23,42,0.08)] sm:p-6">
            <div className="mb-6 flex flex-col gap-3 border-b border-slate-100 pb-5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h2 className="text-lg font-bold text-slate-950">General Config</h2>
                    <p className="mt-1 text-sm text-slate-500">
                        Detector, camera, UART, and zone state machine parameters
                    </p>
                </div>
            </div>

            <div className="space-y-5">
                <CameraConfig
                    inputClass={inputClass}
                    labelClass={labelClass}
                />
                <AIConfig />
                <UartConfig
                    inputClass={inputClass}
                    labelClass={labelClass}
                />
                <ZoneStateMachineConfig />
            </div>
        </section>
    )
}

export default GeneralConfig
