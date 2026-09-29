/* src/pages/CarbonPage.tsx
 * Feature 5 — Carbon & Energy Tracker
 *
 * Shows:
 *  - Field-level CO₂ intensity KPI bar (6 tiles)
 *  - Per-well CO₂/bbl and cost/bbl bar charts (ECharts)
 *  - Editable assumptions panel (boiler efficiency, emission factors, prices)
 *  - Provenance badges on every number
 *  - Disclaimer banner (LITERATURE_ASSUMPTION for all emission factors)
 */
import { useState, useCallback, useEffect } from 'react'
import ReactECharts from 'echarts-for-react'
import { carbonApi, FieldCarbonReport, CarbonAssumptions } from '@/api/features'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import clsx from 'clsx'

// ── CO₂ bar chart ─────────────────────────────────────────────────────────────
function Co2Chart({ report }: { report: FieldCarbonReport }) {
  const wells = report.wells
  const wellIds = wells.map(w => w.well_id)
  const co2Vals = wells.map(w => w.co2_per_bbl_kg)
  const costVals = wells.map(w => w.cost_per_bbl_inr)

  const option = {
    backgroundColor: 'transparent',
    grid: { top: 32, right: 16, bottom: 36, left: 56 },
    legend: {
      data: ['CO₂/bbl (kg)', 'Cost/bbl (₹, /10)'],
      textStyle: { color: '#8b949e', fontSize: 9 },
      top: 4,
    },
    xAxis: {
      type: 'category',
      data: wellIds,
      axisLabel: { color: '#8b949e', fontSize: 9, rotate: 30 },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#8b949e', fontSize: 9 },
      splitLine: { lineStyle: { color: '#30363d', type: 'dashed' } },
    },
    series: [
      {
        name: 'CO₂/bbl (kg)',
        type: 'bar',
        data: co2Vals.map(v => +v.toFixed(2)),
        itemStyle: { color: '#f85149' },
        barGap: '10%',
      },
      {
        name: 'Cost/bbl (₹, /10)',
        type: 'bar',
        data: costVals.map(v => +(v / 10).toFixed(1)),
        itemStyle: { color: '#388bfd' },
        barGap: '10%',
      },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 10 },
      formatter: (params: unknown[]) => {
        const ps = params as Array<{ name: string; seriesName: string; value: number }>
        const well = ps[0]?.name ?? ''
        const co2 = ps.find(p => p.seriesName.includes('CO₂'))?.value ?? 0
        const cost = (ps.find(p => p.seriesName.includes('Cost'))?.value ?? 0) * 10
        return `<b>${well}</b><br/>CO₂/bbl: ${co2.toFixed(2)} kg<br/>Cost/bbl: ₹${cost.toFixed(0)}`
      },
    },
  }

  return (
    <ReactECharts option={option} style={{ height: 220, width: '100%' }} opts={{ renderer: 'canvas' }} />
  )
}

// ── CO₂ breakdown donut ───────────────────────────────────────────────────────
function BreakdownChart({ report }: { report: FieldCarbonReport }) {
  const totalSteam = report.wells.reduce((s, w) => s + w.co2_steam_t, 0)
  const totalElec  = report.wells.reduce((s, w) => s + w.co2_elec_t, 0)

  const option = {
    backgroundColor: 'transparent',
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: [
        { name: 'Steam (gas boiler)', value: +totalSteam.toFixed(3), itemStyle: { color: '#f85149' } },
        { name: 'Electricity (SRP)', value: +totalElec.toFixed(3),  itemStyle: { color: '#388bfd' } },
      ],
      label: { color: '#8b949e', fontSize: 9 },
      emphasis: { label: { show: true, fontSize: 11, color: '#e6edf3' } },
    }],
    tooltip: {
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 10 },
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}: ${p.value.toFixed(3)} tCO₂ (${p.percent?.toFixed(1)}%)`,
    },
  }

  return (
    <ReactECharts option={option} style={{ height: 180, width: '100%' }} opts={{ renderer: 'canvas' }} />
  )
}

// ── Editable assumptions row ──────────────────────────────────────────────────
function AssumptionsEditor({
  assumptions,
  onSave,
}: {
  assumptions: CarbonAssumptions
  onSave: (updates: Record<string, number>) => void
}) {
  const [vals, setVals] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  const editable: Array<{ key: keyof CarbonAssumptions; label: string; unit: string }> = [
    { key: 'boiler_efficiency',              label: 'Boiler Efficiency',      unit: 'fraction' },
    { key: 'emission_factor_gas_kg_per_gj',  label: 'Gas Emission Factor',    unit: 'kg CO₂/GJ' },
    { key: 'grid_emission_factor_kg_per_kwh',label: 'Grid Emission Factor',   unit: 'kg CO₂/kWh' },
    { key: 'gas_price_inr_per_gj',           label: 'Gas Price',              unit: '₹/GJ' },
    { key: 'elec_price_inr_per_kwh',         label: 'Electricity Price',      unit: '₹/kWh' },
    { key: 'steam_temp_c',                   label: 'Steam Temperature',      unit: '°C' },
  ]

  const handleSave = async () => {
    const updates: Record<string, number> = {}
    for (const [k, v] of Object.entries(vals)) {
      const n = parseFloat(v)
      if (!isNaN(n) && n > 0) updates[k] = n
    }
    if (Object.keys(updates).length === 0) return
    setSaving(true)
    try {
      await onSave(updates)
      setVals({})
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {editable.map(({ key, label, unit }) => (
          <div key={key as string} className="card-sm">
            <p className="kpi-label mb-1">{label}</p>
            <div className="flex items-center gap-1">
              <input
                type="number"
                step="any"
                placeholder={String(assumptions[key])}
                value={vals[key as string] ?? ''}
                onChange={e => setVals(prev => ({ ...prev, [key as string]: e.target.value }))}
                className="flex-1 min-w-0 bg-bg border border-border rounded px-1.5 py-0.5 text-xs text-text tabular-nums"
              />
              <span className="text-[10px] text-muted shrink-0">{unit}</span>
            </div>
            <p className="text-[10px] text-muted/60 mt-0.5">
              Current: {String(assumptions[key])}
            </p>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving || Object.keys(vals).length === 0}
          className="btn-primary text-xs px-3 py-1"
        >
          {saving ? '⏳ Saving…' : '✓ Apply Changes'}
        </button>
        <span className="text-[10px] text-muted self-center italic">
          Updates take effect immediately. Not persisted on restart.
        </span>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function CarbonPage() {
  const [report,      setReport]      = useState<FieldCarbonReport | null>(null)
  const [assumptions, setAssumptions] = useState<CarbonAssumptions | null>(null)
  const [periodDays,  setPeriodDays]  = useState(1)
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [r, a] = await Promise.all([
        carbonApi.getFieldCarbon(periodDays),
        carbonApi.getAssumptions(),
      ])
      setReport(r)
      setAssumptions(a)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [periodDays])

  useEffect(() => { loadData() }, [loadData])

  const handleSaveAssumptions = useCallback(async (updates: Record<string, number>) => {
    const r = await carbonApi.updateAssumptions(updates)
    setAssumptions(r)
    // Reload carbon report with new assumptions
    const newReport = await carbonApi.getFieldCarbon(periodDays)
    setReport(newReport)
  }, [periodDays])

  const ft = report?.field_totals

  return (
    <div className="p-4 max-w-6xl mx-auto space-y-4">

      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-text">Carbon & Energy Tracker</h1>
        <ProvenanceBadge tag="LITERATURE_ASSUMPTION" />
        <ProvenanceBadge tag="SIMULATED_LIVE" />
        <span className="text-xs text-muted italic">
          IPCC 2006 · CEA India Grid Factor · Butler 1991 steam enthalpy
        </span>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-xs text-muted">Period:</label>
          <select
            value={periodDays}
            onChange={e => setPeriodDays(Number(e.target.value))}
            className="bg-surface border border-border rounded px-2 py-0.5 text-xs text-text"
          >
            {[1, 7, 30, 90].map(d => (
              <option key={d} value={d}>{d} day{d > 1 ? 's' : ''}</option>
            ))}
          </select>
          <button onClick={loadData} disabled={loading} className="btn-secondary text-xs">
            {loading ? '⏳' : '↻'}
          </button>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="card border-amber-700/40 bg-amber-900/10 px-3 py-2 text-[10px] text-amber-400/80 italic">
        ⚠ All emission factors and energy prices are LITERATURE_ASSUMPTION.
        NOT validated against real Baghewala field energy or emissions data.
        Edit assumptions below to use site-specific values.
      </div>

      {error && (
        <div className="card border-red-700/50 bg-red-900/20 text-red-400 text-xs px-3 py-2">{error}</div>
      )}

      {/* Field KPI bar */}
      {ft && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {[
            { label: 'Total CO₂',           value: `${ft.total_co2_t.toFixed(3)} t`,        prov: 'LITERATURE_ASSUMPTION' as const },
            { label: 'CO₂/bbl',             value: `${ft.field_co2_per_bbl_kg.toFixed(2)} kg/bbl`, prov: 'LITERATURE_ASSUMPTION' as const },
            { label: 'vs Baseline (60 kg)', value: `${ft.co2_delta_vs_baseline_pct >= 0 ? '+' : ''}${ft.co2_delta_vs_baseline_pct.toFixed(1)}%`, prov: 'DEMO_RESULT' as const },
            { label: 'Total Cost',           value: `₹${(ft.total_cost_inr / 1000).toFixed(1)}k`,  prov: 'LITERATURE_ASSUMPTION' as const },
            { label: 'Cost/bbl',             value: `₹${ft.field_cost_per_bbl_inr.toFixed(0)}`,    prov: 'LITERATURE_ASSUMPTION' as const },
            { label: 'Total Oil',            value: `${ft.total_oil_bbl.toFixed(0)} bbl`,           prov: 'SIMULATED_LIVE' as const },
            { label: 'Wells',                value: String(ft.n_wells),                             prov: 'SIMULATED_LIVE' as const },
          ].map(({ label, value, prov }) => (
            <div key={label} className="card-sm">
              <p className="kpi-label mb-1">{label}</p>
              <p className={clsx(
                'text-base font-bold tabular-nums',
                label.includes('vs Baseline') && ft.co2_delta_vs_baseline_pct < 0 ? 'text-green-400' :
                label.includes('vs Baseline') && ft.co2_delta_vs_baseline_pct > 0 ? 'text-red-400' :
                'text-text'
              )}>{value}</p>
              <ProvenanceBadge tag={prov} className="mt-1" />
            </div>
          ))}
        </div>
      )}

      {/* Charts row */}
      {report && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Per-well bars */}
          <div className="lg:col-span-2 card">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-bold text-text">CO₂ Intensity & Cost per Well</h2>
              <ProvenanceBadge tag="LITERATURE_ASSUMPTION" />
            </div>
            <Co2Chart report={report} />
            <p className="text-[9px] text-muted/50 italic mt-1">
              Cost/bbl bar scaled ÷10 for readability. Baseline: 60 kg CO₂/bbl [LITERATURE_ASSUMPTION].
            </p>
          </div>

          {/* Breakdown donut */}
          <div className="card">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-bold text-text">CO₂ Source Breakdown</h2>
              <ProvenanceBadge tag="LITERATURE_ASSUMPTION" />
            </div>
            <BreakdownChart report={report} />
            <p className="text-[9px] text-muted/50 italic mt-1">
              Steam = natural gas boiler emissions. Elec = grid-connected SRP motor.
            </p>
          </div>
        </div>
      )}

      {/* Editable assumptions */}
      {assumptions && (
        <div className="card">
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-sm font-bold text-text">Emission Factor Assumptions</h2>
            <ProvenanceBadge tag="LITERATURE_ASSUMPTION" />
            <span className="text-[10px] text-muted italic">
              {assumptions.sources}
            </span>
          </div>
          <AssumptionsEditor assumptions={assumptions} onSave={handleSaveAssumptions} />
        </div>
      )}

      {/* Per-well table */}
      {report && (
        <div className="card overflow-hidden">
          <h2 className="text-sm font-bold text-text mb-2">Per-Well Carbon Detail</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-muted">
                  <th className="py-1.5 px-2 text-left">Well</th>
                  <th className="py-1.5 px-2 text-right">Steam (m³)</th>
                  <th className="py-1.5 px-2 text-right">Fuel (GJ)</th>
                  <th className="py-1.5 px-2 text-right">CO₂ Steam (t)</th>
                  <th className="py-1.5 px-2 text-right">CO₂ Elec (t)</th>
                  <th className="py-1.5 px-2 text-right">CO₂/bbl (kg)</th>
                  <th className="py-1.5 px-2 text-right">Cost/bbl (₹)</th>
                  <th className="py-1.5 px-2 text-right">SOR</th>
                </tr>
              </thead>
              <tbody>
                {report.wells.map(w => (
                  <tr key={w.well_id} className="border-b border-border/40 hover:bg-surface/50">
                    <td className="py-1.5 px-2 font-bold text-text">{w.well_id}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{w.steam_volume_m3.toFixed(0)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{w.fuel_energy_gj.toFixed(2)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-red-400">{w.co2_steam_t.toFixed(3)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-blue-400">{w.co2_elec_t.toFixed(3)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums font-bold">{w.co2_per_bbl_kg.toFixed(2)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{w.cost_per_bbl_inr.toFixed(0)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{w.sor.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[9px] text-muted/50 italic mt-2">
            PROVENANCE: LITERATURE_ASSUMPTION (all emission factors). NOT validated against real Baghewala records.
          </p>
        </div>
      )}
    </div>
  )
}
