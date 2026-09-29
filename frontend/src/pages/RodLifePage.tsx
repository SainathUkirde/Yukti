/* src/pages/RodLifePage.tsx
 * Feature 2 — Rod Fatigue & Remaining-Life Tracker
 *
 * Shows:
 *  - Fleet table sorted by urgency (critical first)
 *  - Per-well fatigue detail: damage gauge, remaining life, damage curve,
 *    dominant cause, recommended workover window
 *  - Workover (reset) button
 *  - Provenance badges for all estimates
 */
import { useEffect, useState, useCallback } from 'react'
import { useStore } from '@/store/useStore'
import { api } from '@/api/client'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import ReactECharts from 'echarts-for-react'
import clsx from 'clsx'

interface FatigueReport {
  well_id: string
  cumulative_damage: number
  remaining_life_fraction: number
  remaining_life_days_p50: number
  remaining_life_days_p10: number
  remaining_life_days_p90: number
  damage_rate_per_day: number
  total_cycles: number
  dominant_cause: string
  recommended_workover_window: string
  urgency: 'critical' | 'high' | 'medium' | 'low'
  damage_history_last50: number[]
  current_goodman_ratio?: number
  current_spm?: number
  current_active_fault?: string | null
  phase?: string
  method?: string
}

const URGENCY_COLORS: Record<string, string> = {
  critical: 'text-red-400 border-red-700/50 bg-red-900/20',
  high:     'text-amber-400 border-amber-700/50 bg-amber-900/20',
  medium:   'text-yellow-400 border-yellow-700/50 bg-yellow-900/20',
  low:      'text-green-400 border-green-700/50 bg-green-900/20',
}

const URGENCY_GAUGE_COLOR: Record<string, string> = {
  critical: '#f85149',
  high:     '#d29922',
  medium:   '#e3b341',
  low:      '#3fb950',
}

function DamageGauge({ damage, urgency }: { damage: number; urgency: string }) {
  const color = URGENCY_GAUGE_COLOR[urgency] ?? '#388bfd'
  const pct = Math.min(damage * 100, 100)
  return (
    <div className="relative w-full h-3 bg-border rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  )
}

function DamageCurveChart({ history }: { history: number[] }) {
  // Show cumulative sum of history
  let cum = 0
  const cumData = history.map(d => { cum += d; return +cum.toFixed(8) })

  const option = {
    backgroundColor: 'transparent',
    grid: { top: 20, right: 10, bottom: 24, left: 50 },
    xAxis: {
      type: 'category',
      data: cumData.map((_, i) => i.toString()),
      axisLabel: { show: false },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    yAxis: {
      type: 'value',
      name: 'D',
      nameTextStyle: { color: '#8b949e', fontSize: 9 },
      axisLabel: { color: '#8b949e', fontSize: 9 },
      splitLine: { lineStyle: { color: '#30363d', type: 'dashed' } },
    },
    series: [{
      type: 'line',
      data: cumData,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#388bfd', width: 1.5 },
      areaStyle: { color: 'rgba(56,139,253,0.1)' },
    }],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 10 },
    },
  }
  return (
    <ReactECharts option={option} style={{ height: 100, width: '100%' }} opts={{ renderer: 'canvas' }} />
  )
}

export default function RodLifePage() {
  const { selectedWellId } = useStore()
  const [fleet, setFleet] = useState<FatigueReport[]>([])
  const [selected, setSelected] = useState<FatigueReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [resetting, setResetting] = useState(false)

  const loadFleet = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get<{ wells: FatigueReport[] }>('/field/fatigue')
      setFleet(data.wells)
      // Auto-select current dashboard well
      const target = selectedWellId
        ? data.wells.find(w => w.well_id === selectedWellId)
        : data.wells[0]
      if (target) {
        const detail = await api.get<FatigueReport>(`/wells/${target.well_id}/fatigue`)
        setSelected(detail)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [selectedWellId])

  useEffect(() => { loadFleet() }, [loadFleet])

  const selectWell = async (wellId: string) => {
    const detail = await api.get<FatigueReport>(`/wells/${wellId}/fatigue`)
    setSelected(detail)
  }

  const resetFatigue = async (wellId: string) => {
    if (!confirm(`Simulate rod replacement for ${wellId}? This resets all damage.`)) return
    setResetting(true)
    try {
      await api.post(`/wells/${wellId}/fatigue/reset`, {})
      await loadFleet()
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="p-4 max-w-6xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-text">Rod Life Tracker</h1>
        <ProvenanceBadge tag="SIMULATED_LIVE" />
        <ProvenanceBadge tag="LITERATURE_ASSUMPTION" />
        <span className="text-xs text-muted italic">
          Miner's rule + Basquin S-N + Goodman criterion [Shigley 2011, API Spec 11B]
        </span>
        <button onClick={loadFleet} disabled={loading} className="btn-secondary text-xs ml-auto">
          {loading ? 'Loading…' : '↻ Refresh'}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: Fleet table */}
        <div className="lg:col-span-1 space-y-1.5">
          <p className="text-xs text-muted uppercase tracking-wide font-semibold">
            Fleet — sorted by urgency
          </p>
          {fleet.map(w => (
            <button
              key={w.well_id}
              onClick={() => selectWell(w.well_id)}
              className={clsx(
                'w-full text-left px-3 py-2 rounded border transition-all',
                URGENCY_COLORS[w.urgency],
                selected?.well_id === w.well_id ? 'ring-1 ring-accent' : ''
              )}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs font-bold">{w.well_id}</span>
                <span className="text-[10px] uppercase font-semibold">{w.urgency}</span>
              </div>
              <DamageGauge damage={w.cumulative_damage} urgency={w.urgency} />
              <div className="flex justify-between mt-1">
                <span className="text-[10px] text-muted">D = {(w.cumulative_damage * 100).toFixed(2)}%</span>
                <span className="text-[10px] text-muted">
                  p50: {w.remaining_life_days_p50 > 9000 ? '∞' : `${w.remaining_life_days_p50.toFixed(0)}d`}
                </span>
              </div>
            </button>
          ))}
        </div>

        {/* Right: Detail panel */}
        {selected && (
          <div className="lg:col-span-2 space-y-3">
            <div className="card">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h2 className="text-sm font-bold text-text">{selected.well_id} — Rod Fatigue Detail</h2>
                  <span className={clsx('text-xs font-semibold uppercase', {
                    'text-red-400': selected.urgency === 'critical',
                    'text-amber-400': selected.urgency === 'high',
                    'text-yellow-400': selected.urgency === 'medium',
                    'text-green-400': selected.urgency === 'low',
                  })}>
                    {selected.urgency.toUpperCase()} URGENCY
                  </span>
                </div>
                <button
                  onClick={() => resetFatigue(selected.well_id)}
                  disabled={resetting}
                  className="btn-secondary text-xs"
                  title="Simulate rod replacement (workover)"
                >
                  🔧 Workover (Reset)
                </button>
              </div>

              {/* KPI grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                {[
                  { label: 'Cumulative Damage', value: `${(selected.cumulative_damage * 100).toFixed(2)}%`, prov: 'SIMULATED_LIVE' as const },
                  { label: 'Life Remaining (p50)', value: selected.remaining_life_days_p50 > 9000 ? '∞' : `${selected.remaining_life_days_p50.toFixed(0)} days`, prov: 'LITERATURE_ASSUMPTION' as const },
                  { label: 'Life Remaining (p10)', value: selected.remaining_life_days_p10 > 9000 ? '∞' : `${selected.remaining_life_days_p10.toFixed(0)} days`, prov: 'LITERATURE_ASSUMPTION' as const },
                  { label: 'Total Cycles', value: selected.total_cycles.toLocaleString(), prov: 'SIMULATED_LIVE' as const },
                ].map(({ label, value, prov }) => (
                  <div key={label} className="card-sm">
                    <p className="kpi-label mb-1">{label}</p>
                    <p className="text-base font-bold text-text tabular-nums">{value}</p>
                    <ProvenanceBadge tag={prov} className="mt-1" />
                  </div>
                ))}
              </div>

              {/* Workover recommendation */}
              <div className={clsx('px-3 py-2 rounded border text-xs mb-3',
                URGENCY_COLORS[selected.urgency]
              )}>
                <span className="font-semibold">Recommended Workover Window: </span>
                {selected.recommended_workover_window}
                <ProvenanceBadge tag="DEMO_RESULT" className="ml-2" />
              </div>

              {/* Damage bar */}
              <div className="mb-3">
                <div className="flex justify-between text-xs text-muted mb-1">
                  <span>Damage accumulation (Miner's D)</span>
                  <span>{(selected.cumulative_damage * 100).toFixed(3)}% of failure threshold</span>
                </div>
                <DamageGauge damage={selected.cumulative_damage} urgency={selected.urgency} />
                <div className="flex justify-between text-[10px] text-muted mt-0.5">
                  <span>0%</span><span>Failure at 100%</span>
                </div>
              </div>

              {/* Damage curve */}
              {selected.damage_history_last50.length > 2 && (
                <div>
                  <p className="text-xs text-muted mb-1">Damage accumulation curve (last 50 ticks)</p>
                  <DamageCurveChart history={selected.damage_history_last50} />
                </div>
              )}

              {/* Metadata */}
              <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
                <div>
                  <span className="text-muted">Dominant cause: </span>
                  <span className="text-text">{selected.dominant_cause.replace(/_/g, ' ')}</span>
                </div>
                {selected.current_goodman_ratio !== undefined && (
                  <div>
                    <span className="text-muted">Goodman ratio: </span>
                    <span className={clsx('font-mono font-bold',
                      selected.current_goodman_ratio >= 1 ? 'text-red-400' : 'text-green-400'
                    )}>
                      {selected.current_goodman_ratio.toFixed(3)}
                    </span>
                  </div>
                )}
                {selected.current_active_fault && (
                  <div>
                    <span className="text-muted">Active fault: </span>
                    <span className="text-red-400 font-semibold">
                      {selected.current_active_fault.replace(/_/g, ' ')}
                    </span>
                  </div>
                )}
              </div>

              {/* Physics method note */}
              {selected.method && (
                <p className="text-[9px] text-muted/60 mt-3 italic">{selected.method}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
