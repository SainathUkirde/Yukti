/* src/components/panels/OptimizerPanel.tsx
 * Joint CSS+SRP optimizer panel — run Optuna optimization and see recommendations.
 */
import { useState } from 'react'
import { useStore } from '@/store/useStore'
import { optimizerApi } from '@/api/optimizer'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import clsx from 'clsx'

function DeltaRow({ label, value, unit = '%', invert = false }: {
  label: string; value: number; unit?: string; invert?: boolean
}) {
  // invert: positive = bad (e.g. SOR increase)
  const isGood = invert ? value <= 0 : value >= 0
  const color = isGood ? 'text-green-400' : 'text-red-400'
  const sign = value > 0 ? '+' : ''
  return (
    <div className="flex justify-between items-center py-0.5 border-b border-border/30 last:border-0">
      <span className="text-xs text-muted">{label}</span>
      <span className={clsx('text-xs font-bold tabular-nums', color)}>
        {sign}{value.toFixed(1)}{unit}
      </span>
    </div>
  )
}

export function OptimizerPanel() {
  const { selectedWellId, optimizationResults, setOptimizationResult, optimizing, setOptimizing } = useStore()
  const result = selectedWellId ? optimizationResults[selectedWellId] : null

  const [nTrials, setNTrials] = useState(60)
  const [objective, setObjective] = useState<'min_cost_per_bbl' | 'max_oil' | 'min_sor'>('min_cost_per_bbl')

  const runOptimizer = async () => {
    if (!selectedWellId) return
    setOptimizing(true)
    try {
      const res = await optimizerApi.optimize(selectedWellId, nTrials, objective)
      setOptimizationResult(selectedWellId, res)
    } catch (e) {
      console.error('Optimization failed', e)
    } finally {
      setOptimizing(false)
    }
  }

  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-muted uppercase tracking-wide">
          Joint Optimizer
        </span>
        <ProvenanceBadge tag="OPTIMIZER_RECOMMENDATION" />
      </div>

      {!selectedWellId && (
        <p className="text-xs text-muted italic">Select a well first</p>
      )}

      {selectedWellId && (
        <>
          {/* Controls */}
          <div className="space-y-2 mb-3">
            <div>
              <label className="text-[10px] text-muted block mb-0.5">Objective</label>
              <select
                value={objective}
                onChange={(e) => setObjective(e.target.value as typeof objective)}
                className="input text-xs"
              >
                <option value="min_cost_per_bbl">Min Cost / bbl</option>
                <option value="max_oil">Max Oil Rate</option>
                <option value="min_sor">Min SOR</option>
              </select>
            </div>
            <div>
              <label className="text-[10px] text-muted block mb-0.5">Trials: {nTrials}</label>
              <input
                type="range" min={20} max={200} step={20}
                value={nTrials}
                onChange={(e) => setNTrials(+e.target.value)}
                className="w-full h-1.5 accent-accent cursor-pointer"
              />
            </div>
          </div>

          <button
            onClick={runOptimizer}
            disabled={optimizing}
            className="btn-primary w-full mb-3"
          >
            {optimizing ? `Optimizing (${nTrials} trials)…` : '▶ Run Optimizer'}
          </button>

          {/* Results */}
          {result && (
            <div className="flex-1 overflow-y-auto space-y-3">
              {/* KPI Deltas */}
              <div>
                <span className="text-[10px] text-muted uppercase tracking-wide">Expected KPI Δ</span>
                <div className="mt-1">
                  <DeltaRow label="Oil Rate"    value={result.kpi_deltas.oil_rate_delta_pct} />
                  <DeltaRow label="SOR"         value={result.kpi_deltas.sor_delta_pct}      invert />
                  <DeltaRow label="Energy"      value={result.kpi_deltas.energy_delta_pct}   invert />
                  <DeltaRow label="Cost/bbl"    value={result.kpi_deltas.cost_per_bbl_delta_pct} invert />
                  <DeltaRow
                    label="Steam Saved"
                    value={result.kpi_deltas.steam_tonnes_saved_per_cycle}
                    unit=" t/cycle"
                  />
                </div>
              </div>

              {/* Best CSS */}
              <div>
                <span className="text-[10px] text-muted uppercase tracking-wide">Recommended CSS</span>
                <div className="mt-1 space-y-0.5">
                  {Object.entries(result.best_css).map(([k, v]) => (
                    <div key={k} className="flex justify-between text-xs">
                      <span className="text-muted">{k.replace(/_/g, ' ')}</span>
                      <span className="text-text font-mono tabular-nums">{(v as number).toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Best SRP */}
              <div>
                <span className="text-[10px] text-muted uppercase tracking-wide">Recommended SRP</span>
                <div className="mt-1 space-y-0.5">
                  {Object.entries(result.best_srp).map(([k, v]) => (
                    <div key={k} className="flex justify-between text-xs">
                      <span className="text-muted">{k.replace(/_/g, ' ')}</span>
                      <span className="text-text font-mono tabular-nums">{(v as number).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Constraint status */}
              <div className={clsx(
                'px-2 py-1.5 rounded text-xs border',
                result.constraints_passed
                  ? 'bg-green-900/20 border-green-700/40 text-green-300'
                  : 'bg-red-900/20 border-red-700/40 text-red-300'
              )}>
                {result.constraints_passed ? '✓ All constraints passed' : `⚠ ${result.constraint_violations.length} constraint(s) violated`}
              </div>

              <div className="text-[9px] text-muted/60 text-right">
                {result.n_trials} trials · {result.elapsed_s}s · {result.method.split(' ')[0]}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
