/* src/components/panels/FaultInjectionPanel.tsx
 * Demo panel for injecting and resolving faults.
 */
import { useState } from 'react'
import { useStore } from '@/store/useStore'
import { faultsApi } from '@/api/wells'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'

const FAULT_TYPES = [
  { id: 'rod_floating',     label: 'Rod Floating',     color: 'border-orange-600 text-orange-400' },
  { id: 'pump_off',         label: 'Pump-Off',          color: 'border-red-600 text-red-400' },
  { id: 'gas_interference', label: 'Gas Interference',  color: 'border-yellow-600 text-yellow-400' },
  { id: 'fluid_pound',      label: 'Fluid Pound',       color: 'border-red-600 text-red-400' },
  { id: 'pump_unsetting',   label: 'Pump Unsetting',    color: 'border-purple-600 text-purple-400' },
]

export function FaultInjectionPanel() {
  const { selectedWellId, wellStates } = useStore()
  const [pending, setPending] = useState<string | null>(null)
  const state = selectedWellId ? wellStates[selectedWellId] : null
  const activeFault = state?.active_fault

  const inject = async (faultId: string) => {
    if (!selectedWellId) return
    setPending(faultId)
    try {
      await faultsApi.inject(selectedWellId, faultId, 10)
    } catch (e) {
      console.error('Inject failed', e)
    } finally {
      setPending(null)
    }
  }

  const resolve = async () => {
    if (!selectedWellId) return
    setPending('resolve')
    try {
      await faultsApi.resolve(selectedWellId)
    } catch (e) {
      console.error('Resolve failed', e)
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-muted uppercase tracking-wide">Fault Injection (Demo)</span>
        <ProvenanceBadge tag="DEMO_RESULT" />
      </div>

      {!selectedWellId && (
        <p className="text-xs text-muted italic">Select a well first</p>
      )}

      {selectedWellId && (
        <>
          {activeFault && (
            <div className="mb-2 px-2 py-1.5 bg-red-900/30 border border-red-700/50 rounded">
              <div className="flex justify-between items-center">
                <span className="text-xs text-red-300 font-semibold">
                  Active: {activeFault.replace(/_/g, ' ').toUpperCase()}
                </span>
                <button
                  onClick={resolve}
                  disabled={pending === 'resolve'}
                  className="btn-secondary text-[10px] px-2 py-0.5"
                >
                  Resolve
                </button>
              </div>
              {state && (
                <div className="mt-1 text-[10px] text-muted">
                  Severity: {(state.fault_severity * 100).toFixed(0)}%
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 gap-1.5 flex-1">
            {FAULT_TYPES.map((ft) => (
              <button
                key={ft.id}
                onClick={() => inject(ft.id)}
                disabled={pending === ft.id || activeFault === ft.id}
                className={`btn border ${ft.color} bg-transparent hover:bg-white/5 disabled:opacity-40 text-left text-xs`}
              >
                {pending === ft.id ? 'Injecting…' : `⚡ ${ft.label}`}
              </button>
            ))}
          </div>

          <p className="text-[9px] text-muted/60 mt-2 italic">
            Faults ramp in over ~10 ticks. Watch the dyno card change shape.
          </p>
        </>
      )}
    </div>
  )
}
