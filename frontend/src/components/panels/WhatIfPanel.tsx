/* src/components/panels/WhatIfPanel.tsx
 * What-If slider panel — adjust CSS/SRP params and see physics-based KPI projection.
 * Uses WhatIfEngine (surrogate-based, NOT hard-coded deltas).
 */
import { useState } from 'react'
import { useStore } from '@/store/useStore'
import { optimizerApi } from '@/api/optimizer'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import clsx from 'clsx'

interface SliderConfig {
  key: string
  label: string
  min: number
  max: number
  step: number
  unit: string
  defaultFn?: (state: unknown) => number
}

const SLIDERS: SliderConfig[] = [
  { key: 'spm',                   label: 'SPM',              min: 1.5,  max: 10,    step: 0.5,  unit: 'str/min' },
  { key: 'stroke_length_m',       label: 'Stroke Length',    min: 0.5,  max: 5,     step: 0.1,  unit: 'm' },
  { key: 'vfd_frequency_hz',      label: 'VFD Frequency',    min: 20,   max: 60,    step: 1,    unit: 'Hz' },
  { key: 'steam_volume_cwe_m3',   label: 'Steam Volume',     min: 100,  max: 1000,  step: 50,   unit: 'm³' },
  { key: 'soak_days',             label: 'Soak Days',        min: 5,    max: 30,    step: 1,    unit: 'days' },
  { key: 'injection_pressure_kpa',label: 'Injection Press',  min: 2000, max: 6000,  step: 100,  unit: 'kPa' },
]

function DeltaBadge({ value, unit = '%' }: { value: number; unit?: string }) {
  const color = value > 0 ? 'text-green-400' : value < 0 ? 'text-red-400' : 'text-muted'
  const sign = value > 0 ? '+' : ''
  return <span className={clsx('text-xs font-bold tabular-nums', color)}>{sign}{value.toFixed(1)}{unit}</span>
}

export function WhatIfPanel() {
  const { selectedWellId, wellStates, setWhatIfResult, whatIfResult, whatIfPending, setWhatIfPending } = useStore()
  const state = selectedWellId ? wellStates[selectedWellId] : null

  const [overrides, setOverrides] = useState<Record<string, number>>({})

  const getDefault = (key: string): number => {
    if (!state) return 5
    const cfg = state.config as unknown as Record<string, number>
    return cfg[key] ?? 5
  }

  const setValue = (key: string, val: number) => {
    setOverrides((prev) => ({ ...prev, [key]: val }))
  }

  const runWhatIf = async () => {
    if (!selectedWellId || Object.keys(overrides).length === 0) return
    setWhatIfPending(true)
    try {
      const result = await optimizerApi.whatif(selectedWellId, overrides)
      setWhatIfResult(result)
    } catch (e) {
      console.error('WhatIf failed', e)
    } finally {
      setWhatIfPending(false)
    }
  }

  const resetAll = () => {
    setOverrides({})
    setWhatIfResult(null)
  }

  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-muted uppercase tracking-wide">What-If Analysis</span>
        <ProvenanceBadge tag="OPTIMIZER_RECOMMENDATION" />
      </div>

      {!state && (
        <p className="text-xs text-muted italic">Select a well first</p>
      )}

      {state && (
        <>
          <div className="flex-1 overflow-y-auto space-y-3">
            {SLIDERS.map((s) => {
              const base = getDefault(s.key)
              const val = overrides[s.key] ?? base
              return (
                <div key={s.key}>
                  <div className="flex justify-between items-center mb-0.5">
                    <span className="text-xs text-muted">{s.label}</span>
                    <div className="flex items-center gap-1">
                      {overrides[s.key] !== undefined && (
                        <span className="text-[10px] text-muted/60 line-through tabular-nums">{base.toFixed(1)}</span>
                      )}
                      <span className="text-xs font-bold tabular-nums text-text">{val.toFixed(1)}</span>
                      <span className="text-[10px] text-muted">{s.unit}</span>
                    </div>
                  </div>
                  <input
                    type="range"
                    min={s.min}
                    max={s.max}
                    step={s.step}
                    value={val}
                    onChange={(e) => setValue(s.key, parseFloat(e.target.value))}
                    className="w-full h-1.5 accent-accent cursor-pointer"
                  />
                </div>
              )
            })}
          </div>

          <div className="flex gap-2 mt-3">
            <button
              onClick={runWhatIf}
              disabled={whatIfPending || Object.keys(overrides).length === 0}
              className="btn-primary flex-1"
            >
              {whatIfPending ? 'Computing…' : 'Run What-If'}
            </button>
            <button onClick={resetAll} className="btn-secondary">Reset</button>
          </div>

          {/* Results */}
          {whatIfResult && (
            <div className="mt-3 border-t border-border pt-3 space-y-1.5">
              <span className="text-[10px] text-muted uppercase tracking-wide">Projected Δ KPIs</span>
              {[
                { label: 'Oil Rate',      val: whatIfResult.deltas.oil_rate_pct },
                { label: 'SOR',           val: whatIfResult.deltas.sor_pct },
                { label: 'Energy',        val: whatIfResult.deltas.kwh_per_bbl_pct },
                { label: 'Pump Eff',      val: whatIfResult.deltas.pump_efficiency_pct },
                { label: 'Viscosity',     val: whatIfResult.deltas.viscosity_pct },
              ].map(({ label, val }) => (
                <div key={label} className="flex justify-between items-center">
                  <span className="text-xs text-muted">{label}</span>
                  <DeltaBadge value={val} />
                </div>
              ))}
              {whatIfResult.rod_floating_risk_after && (
                <div className="px-2 py-1 bg-red-900/30 rounded text-xs text-red-300">
                  ⚠ Rod floating risk after change!
                </div>
              )}
              <div className="flex flex-wrap gap-1 mt-1">
                {(whatIfResult.narrative as string[]).slice(0, 3).map((line, i) => (
                  <span key={i} className="text-[9px] text-muted/70 italic block w-full">{line}</span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
