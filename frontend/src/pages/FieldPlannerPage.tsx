/* src/pages/FieldPlannerPage.tsx
 * Feature 1 — Field-Level Steam Allocator & CSS Scheduler
 *
 * Shows:
 *  - Steam budget slider + generator capacity slider
 *  - "Run Allocation" button → calls POST /field/allocate
 *  - Well ranking table with marginal value column + rod fatigue flags
 *  - Gantt-style schedule (horizontal bar chart via ECharts)
 *  - Baseline vs Optimised grouped bar chart
 *  - Field-level KPI summary (total steam, total oil, SOR, % gain)
 *  - Per-well explanation tooltips
 *  - Provenance badges throughout
 */
import { useState, useCallback } from 'react'
import ReactECharts from 'echarts-for-react'
import { allocatorApi, AllocationResult, WellAllocation } from '@/api/features'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import clsx from 'clsx'

// ── Colours ───────────────────────────────────────────────────────────────────
const ROD_CAP_COLOR = 'text-amber-400'
const ROD_OK_COLOR  = 'text-green-400'
const ROD_EX_COLOR  = 'text-red-400'

function rodStatusClass(w: WellAllocation): string {
  if (w.rod_fatigue_damage >= 0.95) return ROD_EX_COLOR
  if (w.rod_life_constraint_applied) return ROD_CAP_COLOR
  return ROD_OK_COLOR
}

function rodStatusLabel(w: WellAllocation): string {
  if (w.rod_fatigue_damage >= 0.95) return '⛔ Excluded'
  if (w.rod_life_constraint_applied) return '⚠ Capped'
  return '✓ OK'
}

// ── Gantt chart (horizontal bar per well) ─────────────────────────────────────
function GanttChart({ allocs, period }: { allocs: WellAllocation[]; period: number }) {
  if (allocs.length === 0) return null
  const yAxis = allocs.map(a => a.well_id)
  // ECharts horizontal bar chart: each bar = [start_day, start_day+duration]
  const data = allocs.map(a => ({
    value: [a.rank - 1, a.start_day, a.start_day + a.duration_days],
    itemStyle: { color: a.rod_life_constraint_applied ? '#d29922' : '#388bfd' },
  }))

  const option = {
    backgroundColor: 'transparent',
    grid: { top: 8, right: 16, bottom: 28, left: 52 },
    xAxis: {
      type: 'value',
      min: 0,
      max: period,
      name: 'Day',
      nameTextStyle: { color: '#8b949e', fontSize: 9 },
      axisLabel: { color: '#8b949e', fontSize: 9 },
      splitLine: { lineStyle: { color: '#30363d', type: 'dashed' } },
    },
    yAxis: {
      type: 'category',
      data: yAxis,
      axisLabel: { color: '#8b949e', fontSize: 10 },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    series: [{
      type: 'custom',
      renderItem: (_params: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[]; size: (v: number[]) => number[]; style: () => unknown }) => {
        const categoryIndex = api.value(0)
        const start = api.coord([api.value(1), categoryIndex])
        const end   = api.coord([api.value(2), categoryIndex])
        const height = api.size([0, 1])[1] * 0.6
        return {
          type: 'rect',
          shape: {
            x: start[0],
            y: start[1] - height / 2,
            width: end[0] - start[0],
            height,
          },
          style: api.style(),
        }
      },
      data,
      encode: { x: [1, 2], y: 0 },
    }],
    tooltip: {
      trigger: 'item',
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 10 },
      formatter: (p: { data: { value: number[] } }) => {
        const d = p.data.value
        const w = allocs[d[0]]
        if (!w) return ''
        return `<b>${w.well_id}</b><br/>Start: Day ${d[1].toFixed(1)}<br/>Duration: ${(d[2] - d[1]).toFixed(1)} days<br/>Steam: ${w.steam_volume_m3.toFixed(0)} m³`
      },
    },
  }

  return (
    <ReactECharts
      option={option}
      style={{ height: Math.max(120, allocs.length * 28), width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  )
}

// ── Baseline vs Optimised comparison bar chart ────────────────────────────────
function ComparisonChart({ result }: { result: AllocationResult }) {
  const optVols  = result.well_allocations.map(w => w.steam_volume_m3)
  const baseVols = result.baseline_allocations.map(w => w.steam_volume_m3)
  const wellIds  = result.well_allocations.map(w => w.well_id)

  const option = {
    backgroundColor: 'transparent',
    grid: { top: 24, right: 12, bottom: 28, left: 44 },
    legend: {
      data: ['Optimised', 'Baseline'],
      textStyle: { color: '#8b949e', fontSize: 9 },
      top: 2,
    },
    xAxis: {
      type: 'category',
      data: wellIds,
      axisLabel: { color: '#8b949e', fontSize: 9, rotate: 30 },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    yAxis: {
      type: 'value',
      name: 'm³',
      nameTextStyle: { color: '#8b949e', fontSize: 9 },
      axisLabel: { color: '#8b949e', fontSize: 9 },
      splitLine: { lineStyle: { color: '#30363d', type: 'dashed' } },
    },
    series: [
      {
        name: 'Optimised',
        type: 'bar',
        data: optVols,
        itemStyle: { color: '#388bfd' },
        barGap: '10%',
      },
      {
        name: 'Baseline',
        type: 'bar',
        data: baseVols,
        itemStyle: { color: '#484f58' },
        barGap: '10%',
      },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 10 },
    },
  }

  return (
    <ReactECharts option={option} style={{ height: 180, width: '100%' }} opts={{ renderer: 'canvas' }} />
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function FieldPlannerPage() {
  const [budget,      setBudget]      = useState(5000)
  const [genCap,      setGenCap]      = useState(200)
  const [period,      setPeriod]      = useState(30)
  const [loading,     setLoading]     = useState(false)
  const [result,      setResult]      = useState<AllocationResult | null>(null)
  const [error,       setError]       = useState<string | null>(null)
  const [expandedRow, setExpandedRow] = useState<string | null>(null)

  const runAllocation = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await allocatorApi.allocate(budget, genCap, period)
      setResult(res)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [budget, genCap, period])

  const loadCached = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await allocatorApi.getSchedule()
      setResult(res)
    } catch {
      setError('No cached schedule found. Run allocation first.')
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div className="p-4 max-w-7xl mx-auto space-y-4">

      {/* ── Header ── */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-text">Field Steam Planner</h1>
        <ProvenanceBadge tag="OPTIMIZER_RECOMMENDATION" />
        <ProvenanceBadge tag="DEMO_RESULT" />
        <span className="text-xs text-muted italic">
          Greedy marginal-value knapsack [Butler 1991] · real physics surrogate
        </span>
        <button onClick={loadCached} disabled={loading} className="btn-secondary text-xs ml-auto">
          ↻ Load Last
        </button>
      </div>

      {/* ── Controls ── */}
      <div className="card grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className="kpi-label block mb-1">
            Steam Budget — {budget.toLocaleString()} m³ CWE
          </label>
          <input
            type="range" min={500} max={20000} step={100}
            value={budget}
            onChange={e => setBudget(Number(e.target.value))}
            className="w-full accent-accent"
          />
          <div className="flex justify-between text-[10px] text-muted mt-0.5">
            <span>500</span><span>20 000 m³</span>
          </div>
        </div>

        <div>
          <label className="kpi-label block mb-1">
            Generator Capacity — {genCap} m³/day
          </label>
          <input
            type="range" min={50} max={1000} step={10}
            value={genCap}
            onChange={e => setGenCap(Number(e.target.value))}
            className="w-full accent-accent"
          />
          <div className="flex justify-between text-[10px] text-muted mt-0.5">
            <span>50</span><span>1 000 m³/day</span>
          </div>
        </div>

        <div>
          <label className="kpi-label block mb-1">
            Planning Period — {period} days
          </label>
          <input
            type="range" min={7} max={90} step={1}
            value={period}
            onChange={e => setPeriod(Number(e.target.value))}
            className="w-full accent-accent"
          />
          <div className="flex justify-between text-[10px] text-muted mt-0.5">
            <span>7</span><span>90 days</span>
          </div>
        </div>

        <div className="sm:col-span-3 flex gap-2 pt-1">
          <button
            onClick={runAllocation}
            disabled={loading}
            className="btn-primary text-sm px-5 py-1.5"
          >
            {loading ? '⏳ Allocating…' : '▶ Run Allocation'}
          </button>
          {result && (
            <span className="text-xs text-green-400 self-center">
              ✓ Last run: {result.well_allocations.length} wells · {result.total_steam_allocated_m3.toFixed(0)} m³
            </span>
          )}
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="card border-red-700/50 bg-red-900/20 text-red-400 text-xs px-3 py-2">
          {error}
        </div>
      )}

      {/* ── Results ── */}
      {result && (
        <div className="space-y-4">

          {/* KPI bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            {[
              { label: 'Steam Allocated', value: `${result.total_steam_allocated_m3.toFixed(0)} m³`, prov: 'OPTIMIZER_RECOMMENDATION' as const },
              { label: 'Budget Used', value: `${(result.total_steam_allocated_m3 / result.total_steam_budget_m3 * 100).toFixed(1)}%`, prov: 'OPTIMIZER_RECOMMENDATION' as const },
              { label: 'Exp. Total Oil', value: `${result.expected_total_oil_m3.toFixed(1)} m³`, prov: 'OPTIMIZER_RECOMMENDATION' as const },
              { label: 'Field SOR', value: result.expected_field_sor.toFixed(2), prov: 'OPTIMIZER_RECOMMENDATION' as const },
              { label: 'Oil Gain vs Baseline', value: `${result.oil_gain_vs_baseline_pct >= 0 ? '+' : ''}${result.oil_gain_vs_baseline_pct.toFixed(1)}%`, prov: 'DEMO_RESULT' as const },
              { label: 'Excluded (rod)', value: result.wells_excluded_rod_fatigue.length.toString(), prov: 'SIMULATED_LIVE' as const },
            ].map(({ label, value, prov }) => (
              <div key={label} className="card-sm">
                <p className="kpi-label mb-1">{label}</p>
                <p className="text-base font-bold text-text tabular-nums">{value}</p>
                <ProvenanceBadge tag={prov} className="mt-1" />
              </div>
            ))}
          </div>

          {/* Excluded wells warning */}
          {result.wells_excluded_rod_fatigue.length > 0 && (
            <div className="card border-red-700/50 bg-red-900/10 text-xs px-3 py-2 flex gap-2 items-start">
              <span className="text-red-400 font-semibold">⛔ Excluded (Miner's D ≥ 0.95):</span>
              <span className="text-red-300">{result.wells_excluded_rod_fatigue.join(', ')}</span>
              <ProvenanceBadge tag="SIMULATED_LIVE" className="ml-auto" />
            </div>
          )}

          {/* Well ranking table */}
          <div className="card overflow-hidden">
            <h2 className="text-sm font-bold text-text mb-2">
              Well Ranking — Marginal Value (highest first)
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-muted">
                    <th className="py-1.5 px-2 text-left">Rank</th>
                    <th className="py-1.5 px-2 text-left">Well</th>
                    <th className="py-1.5 px-2 text-right">Steam (m³)</th>
                    <th className="py-1.5 px-2 text-right">Marginal Oil (m³/m³)</th>
                    <th className="py-1.5 px-2 text-right">Exp. Oil (m³)</th>
                    <th className="py-1.5 px-2 text-right">SOR</th>
                    <th className="py-1.5 px-2 text-right">kWh/bbl</th>
                    <th className="py-1.5 px-2 text-right">Start (d)</th>
                    <th className="py-1.5 px-2 text-right">Inj Dur (d)</th>
                    <th className="py-1.5 px-2 text-center">Rod Status</th>
                    <th className="py-1.5 px-2 text-center">Cstr</th>
                    <th className="py-1.5 px-2 text-center">ℹ</th>
                  </tr>
                </thead>
                <tbody>
                  {result.well_allocations.map(w => (
                    <>
                      <tr
                        key={w.well_id}
                        className={clsx(
                          'border-b border-border/40 hover:bg-surface/50 transition-colors',
                          expandedRow === w.well_id && 'bg-surface/50'
                        )}
                      >
                        <td className="py-1.5 px-2 text-muted font-mono">#{w.rank}</td>
                        <td className="py-1.5 px-2 font-bold text-text">{w.well_id}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{w.steam_volume_m3.toFixed(0)}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums text-accent">
                          {w.marginal_oil_per_m3_steam.toFixed(4)}
                        </td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{w.expected_oil_m3.toFixed(2)}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{w.expected_sor.toFixed(2)}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{w.expected_kwh_per_bbl.toFixed(1)}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{w.start_day.toFixed(1)}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{w.duration_days.toFixed(1)}</td>
                        <td className={clsx('py-1.5 px-2 text-center text-[10px] font-semibold', rodStatusClass(w))}>
                          {rodStatusLabel(w)}
                        </td>
                        <td className={clsx('py-1.5 px-2 text-center text-[10px]',
                          w.constraints_passed ? 'text-green-400' : 'text-red-400'
                        )}>
                          {w.constraints_passed ? '✓' : `✗ ${w.constraint_violations.length}`}
                        </td>
                        <td className="py-1.5 px-2 text-center">
                          <button
                            onClick={() => setExpandedRow(expandedRow === w.well_id ? null : w.well_id)}
                            className="text-muted hover:text-accent text-xs"
                            title="Show explanation"
                          >
                            {expandedRow === w.well_id ? '▲' : '▼'}
                          </button>
                        </td>
                      </tr>
                      {expandedRow === w.well_id && (
                        <tr key={`${w.well_id}-exp`} className="bg-surface/30">
                          <td colSpan={12} className="px-4 py-2">
                            <p className="text-xs text-muted/80 italic">{w.explanation}</p>
                            <p className="text-[10px] text-muted/50 mt-1">
                              Rod D = {(w.rod_fatigue_damage * 100).toFixed(2)}% — {w.rod_life_reason}
                            </p>
                            {w.constraint_violations.length > 0 && (
                              <p className="text-[10px] text-red-400 mt-1">
                                Violations: {w.constraint_violations.map(v => v.name).join(', ')}
                              </p>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[9px] text-muted/50 italic mt-2">
              {result.method}
            </p>
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Gantt */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-bold text-text">Injection Schedule (Gantt)</h2>
                <div className="flex gap-2">
                  <span className="inline-flex items-center gap-1 text-[10px] text-muted">
                    <span className="w-2.5 h-2 rounded-sm bg-accent inline-block" />Optimised
                  </span>
                  <span className="inline-flex items-center gap-1 text-[10px] text-muted">
                    <span className="w-2.5 h-2 rounded-sm bg-amber-500 inline-block" />Rod-Capped
                  </span>
                </div>
              </div>
              <GanttChart allocs={result.well_allocations} period={result.period_days} />
              <ProvenanceBadge tag="OPTIMIZER_RECOMMENDATION" className="mt-2" />
            </div>

            {/* Bar comparison */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-bold text-text">Steam Allocation — Optimised vs Baseline</h2>
                <ProvenanceBadge tag="DEMO_RESULT" />
              </div>
              <ComparisonChart result={result} />
              <p className="text-[9px] text-muted/50 italic mt-1">
                Baseline = equal-split. Both evaluated with real physics surrogate.
              </p>
            </div>
          </div>

        </div>
      )}

      {/* Empty state */}
      {!result && !loading && !error && (
        <div className="card text-center py-12 text-muted text-sm">
          <p className="text-2xl mb-2">🛢️</p>
          <p>Set the steam budget and click <strong>Run Allocation</strong> to generate the field plan.</p>
          <p className="text-xs mt-1 text-muted/60">
            Uses greedy marginal-value knapsack with real physics surrogate + rod fatigue integration.
          </p>
        </div>
      )}
    </div>
  )
}
