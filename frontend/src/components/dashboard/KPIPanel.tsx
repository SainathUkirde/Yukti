/* src/components/dashboard/KPIPanel.tsx
 * Primary KPI panel — shows all 11 required KPIs without scrolling.
 * Phase 8 requirement: 11 KPI items visible without scroll on 1080p.
 */
import { useStore } from '@/store/useStore'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import clsx from 'clsx'

interface KPIItem {
  label: string
  valueKey: string
  unit: string
  format?: (v: number) => string
  threshold?: { warn: number; danger: number; invert?: boolean }
  prov?: string
}

const KPI_ITEMS: KPIItem[] = [
  {
    label: 'Reservoir Temp',
    valueKey: 'reservoir_temp_c',
    unit: '°C',
    threshold: { warn: 80, danger: 55, invert: true }, // lower = worse
  },
  {
    label: 'Oil Viscosity',
    valueKey: 'oil_viscosity_cp',
    unit: 'cP',
    threshold: { warn: 500, danger: 1500 }, // higher = worse
    format: (v) => v > 999 ? `${(v/1000).toFixed(1)}k` : v.toFixed(0),
  },
  {
    label: 'Oil Rate',
    valueKey: 'oil_rate_m3d',
    unit: 'm³/d',
    format: (v) => v.toFixed(2),
    threshold: { warn: 3, danger: 1, invert: true },
  },
  {
    label: 'Water Cut',
    valueKey: 'water_cut_fraction',
    unit: '%',
    format: (v) => (v * 100).toFixed(1),
    threshold: { warn: 60, danger: 80 },
  },
  {
    label: 'Steam-Oil Ratio',
    valueKey: 'sor',
    unit: 'bbl/bbl',
    format: (v) => v.toFixed(2),
    threshold: { warn: 4.5, danger: 6.0 },
  },
  {
    label: 'Pump Efficiency',
    valueKey: 'pump_efficiency_fraction',
    unit: '%',
    format: (v) => (v * 100).toFixed(1),
    threshold: { warn: 60, danger: 40, invert: true },
  },
  {
    label: 'Motor Power',
    valueKey: 'motor_power_kw',
    unit: 'kW',
    format: (v) => v.toFixed(1),
    threshold: { warn: 30, danger: 50 },
  },
  {
    label: 'kWh / bbl',
    valueKey: 'kwh_per_bbl',
    unit: 'kWh',
    format: (v) => v.toFixed(2),
    threshold: { warn: 8, danger: 15 },
  },
  {
    label: 'Rod Float Risk',
    valueKey: 'rod_float_risk_score',
    unit: '/100',
    format: (v) => v.toFixed(0),
    threshold: { warn: 40, danger: 70 },
  },
  {
    label: 'Pump Fillage',
    valueKey: 'pump_fillage_fraction',
    unit: '%',
    format: (v) => (v * 100).toFixed(1),
    threshold: { warn: 60, danger: 40, invert: true },
  },
  {
    label: 'Goodman Ratio',
    valueKey: 'goodman_ratio',
    unit: '',
    format: (v) => v.toFixed(3),
    threshold: { warn: 0.7, danger: 1.0 },
  },
]

function colorForValue(item: KPIItem, value: number): string {
  if (!item.threshold) return 'text-text'
  const { warn, danger, invert } = item.threshold
  if (invert) {
    // lower = worse
    if (value <= danger) return 'text-red-400'
    if (value <= warn)   return 'text-amber-400'
    return 'text-green-400'
  } else {
    // higher = worse
    if (value >= danger) return 'text-red-400'
    if (value >= warn)   return 'text-amber-400'
    return 'text-green-400'
  }
}

export function KPIPanel() {
  const { wellStates, selectedWellId } = useStore()
  const state = selectedWellId ? wellStates[selectedWellId] : null

  if (!state) {
    return (
      <div className="card h-full flex items-center justify-center text-muted text-sm">
        Select a well to see KPIs
      </div>
    )
  }

  return (
    <div className="card h-full flex flex-col gap-1">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-muted uppercase tracking-wide">Live KPIs</span>
        <ProvenanceBadge tag="SIMULATED_LIVE" />
      </div>

      <div className="grid grid-cols-1 gap-1 flex-1">
        {KPI_ITEMS.map((item) => {
          const pf = (state as unknown as Record<string, { value: number; unit: string }>)[item.valueKey]
          if (!pf) return null
          const raw = pf.value
          const display = item.format ? item.format(raw) : raw.toFixed(2)
          const color = colorForValue(item, raw)

          return (
            <div key={item.label} className="flex items-center justify-between py-1 border-b border-border/40 last:border-0">
              <span className="text-xs text-muted truncate max-w-[110px]">{item.label}</span>
              <div className="flex items-baseline gap-1">
                <span className={clsx('text-sm font-bold tabular-nums', color)}>
                  {display}
                </span>
                <span className="text-[10px] text-muted">{item.unit}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Active fault indicator */}
      {state.active_fault && (
        <div className="mt-1 px-2 py-1 bg-red-900/40 border border-red-700/50 rounded text-xs text-red-300">
          ⚠ FAULT: {state.active_fault.replace(/_/g, ' ').toUpperCase()}
          {' '}({(state.fault_severity * 100).toFixed(0)}%)
        </div>
      )}
    </div>
  )
}
