/* src/components/dashboard/WellSelector.tsx
 * Multi-well grid selector — shows all wells with status colors.
 */
import { useStore } from '@/store/useStore'
import { PhaseChip } from '@/components/ui/PhaseChip'
import clsx from 'clsx'

const STATUS_DOT: Record<string, string> = {
  green: 'bg-green-400',
  amber: 'bg-amber-400',
  red:   'bg-red-400 animate-pulse',
}

export function WellSelector() {
  const { allWells, selectedWellId, selectWell } = useStore()

  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1">
      {allWells.map((w) => (
        <button
          key={w.well_id}
          onClick={() => selectWell(w.well_id)}
          className={clsx(
            'flex-shrink-0 flex flex-col items-start px-2.5 py-1.5 rounded border text-left',
            'transition-all duration-150 min-w-[90px]',
            selectedWellId === w.well_id
              ? 'border-accent bg-accent/10 text-text'
              : 'border-border bg-surface hover:border-accent/50 text-muted hover:text-text'
          )}
        >
          <div className="flex items-center gap-1.5 w-full">
            <span className={clsx('w-2 h-2 rounded-full flex-shrink-0', STATUS_DOT[w.status_color])} />
            <span className="text-xs font-semibold truncate">{w.well_id}</span>
          </div>
          <PhaseChip phase={w.phase} showIcon={false} className="mt-0.5 text-[9px]" />
          <span className="text-[10px] tabular-nums mt-0.5">
            {w.oil_rate_m3d.toFixed(1)} m³/d
          </span>
        </button>
      ))}
      {allWells.length === 0 && (
        <span className="text-xs text-muted italic">Loading wells…</span>
      )}
    </div>
  )
}
