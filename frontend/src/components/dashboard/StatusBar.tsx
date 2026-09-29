/* src/components/dashboard/StatusBar.tsx
 * Top status bar — connection indicator, well selector, active phase.
 */
import { useStore } from '@/store/useStore'
import { PhaseChip } from '@/components/ui/PhaseChip'
import clsx from 'clsx'

export function StatusBar() {
  const { connected, selectedWellId, wellStates, allWells } = useStore()
  const state = selectedWellId ? wellStates[selectedWellId] : null
  const wellCount = allWells.length

  return (
    <div className="flex items-center gap-3 px-4 py-1.5 bg-surface border-b border-border">
      {/* Logo / Title */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <img src="/yukti-logo.png" alt="YUKTI Logo" className="h-6 w-6 object-contain rounded" />
        <span className="text-sm font-semibold text-text">YUKTI</span>
        <span className="text-[10px] text-muted hidden lg:block">CSS + SRP Optimizer | Heavy Oil</span>
      </div>

      <div className="flex-1" />

      {/* Connection */}
      <div className="flex items-center gap-1.5">
        <span className={clsx(
          'w-2 h-2 rounded-full',
          connected ? 'bg-green-400 animate-pulse-slow' : 'bg-red-400'
        )} />
        <span className="text-[10px] text-muted">{connected ? 'LIVE' : 'OFFLINE'}</span>
      </div>

      {/* Selected well state */}
      {state && (
        <>
          <span className="text-[10px] text-muted hidden md:block">|</span>
          <span className="text-xs font-mono text-text hidden md:block">{state.well_id}</span>
          <PhaseChip phase={state.phase} />
          <span className="text-[10px] text-muted hidden md:block">
            Cycle {state.cycle_number}
          </span>
        </>
      )}

      {/* Well count */}
      <span className="text-[10px] text-muted">
        {wellCount} wells
      </span>

      {/* Synthetic data disclaimer */}
      <span className="text-[9px] bg-amber-900/40 text-amber-400 border border-amber-700/40 px-1.5 py-0.5 rounded hidden lg:block">
        SYNTHETIC DATA
      </span>
    </div>
  )
}
