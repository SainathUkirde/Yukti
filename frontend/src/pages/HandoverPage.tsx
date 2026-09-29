/* src/pages/HandoverPage.tsx
 * Feature 5 (Bonus) — Shift Handover Summary
 *
 * Generates a structured shift handover document from all live simulation data:
 *  - Shift label + operator name inputs
 *  - Executive summary: production rates, fault count, rod fatigue count
 *  - Priority action list (critical → high, colour-coded)
 *  - Active faults list
 *  - Wells status table (phase, viscosity, pump efficiency, SOR)
 *  - Rod fatigue summary (critical / high)
 *  - Allocation + carbon KPI summary tiles
 *  - Print / download button
 */
import { useState, useCallback } from 'react'
import { carbonApi, HandoverDoc } from '@/api/features'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import clsx from 'clsx'

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'border-red-700/50 bg-red-900/20 text-red-300',
  high:     'border-amber-700/50 bg-amber-900/20 text-amber-300',
  medium:   'border-yellow-700/40 bg-yellow-900/10 text-yellow-300',
  info:     'border-border bg-surface/30 text-muted',
}

const PHASE_COLOR: Record<string, string> = {
  production: 'text-green-400',
  injection:  'text-blue-400',
  soak:       'text-yellow-400',
  idle:       'text-muted',
}

export default function HandoverPage() {
  const [shiftLabel,  setShiftLabel]  = useState('Day Shift')
  const [outgoing,    setOutgoing]    = useState('Operator A')
  const [incoming,    setIncoming]    = useState('Operator B')
  const [periodDays,  setPeriodDays]  = useState(1)
  const [doc,         setDoc]         = useState<HandoverDoc | null>(null)
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState<string | null>(null)

  const generate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await carbonApi.getHandover(shiftLabel, outgoing, incoming, periodDays)
      setDoc(d)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [shiftLabel, outgoing, incoming, periodDays])

  const handlePrint = () => window.print()

  return (
    <div className="p-4 max-w-5xl mx-auto space-y-4 print:p-0 print:max-w-none">

      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap print:hidden">
        <h1 className="text-lg font-bold text-text">Shift Handover</h1>
        <ProvenanceBadge tag="DEMO_RESULT" />
        <span className="text-xs text-muted italic">
          Auto-generated from live digital twin — NOT a real operations handover
        </span>
      </div>

      {/* Generation controls */}
      <div className="card grid grid-cols-2 sm:grid-cols-4 gap-3 print:hidden">
        <div>
          <label className="kpi-label block mb-1">Shift</label>
          <select
            value={shiftLabel}
            onChange={e => setShiftLabel(e.target.value)}
            className="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-text"
          >
            {['Day Shift', 'Night Shift', 'Morning Shift', 'Afternoon Shift'].map(s => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="kpi-label block mb-1">Outgoing Operator</label>
          <input
            value={outgoing}
            onChange={e => setOutgoing(e.target.value)}
            className="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-text"
          />
        </div>
        <div>
          <label className="kpi-label block mb-1">Incoming Operator</label>
          <input
            value={incoming}
            onChange={e => setIncoming(e.target.value)}
            className="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-text"
          />
        </div>
        <div>
          <label className="kpi-label block mb-1">Carbon Period</label>
          <select
            value={periodDays}
            onChange={e => setPeriodDays(Number(e.target.value))}
            className="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-text"
          >
            {[1, 7, 30].map(d => <option key={d} value={d}>{d}d</option>)}
          </select>
        </div>

        <div className="sm:col-span-4 flex gap-2">
          <button
            onClick={generate}
            disabled={loading}
            className="btn-primary text-sm px-5 py-1.5"
          >
            {loading ? '⏳ Generating…' : '📋 Generate Handover'}
          </button>
          {doc && (
            <button onClick={handlePrint} className="btn-secondary text-xs">
              🖨 Print / PDF
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="card border-red-700/50 bg-red-900/20 text-red-400 text-xs px-3 py-2">{error}</div>
      )}

      {/* ── Handover document ── */}
      {doc && (
        <div className="space-y-4">

          {/* Document header */}
          <div className="card border-accent/30 bg-accent/5 print:border print:border-gray-300">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
              <div>
                <h2 className="text-base font-bold text-text">
                  {doc.shift_label} Handover — {doc.handover_id}
                </h2>
                <p className="text-xs text-muted">
                  Generated: {new Date(doc.generated_at).toLocaleString()} UTC
                </p>
              </div>
              <div className="text-xs text-right">
                <p><span className="text-muted">Outgoing:</span> <strong className="text-text">{doc.outgoing_operator}</strong></p>
                <p><span className="text-muted">Incoming:</span> <strong className="text-accent">{doc.incoming_operator}</strong></p>
              </div>
            </div>
            <p className="text-[9px] text-amber-400/70 italic mt-1">{doc.disclaimer}</p>
          </div>

          {/* Executive summary */}
          <div>
            <h3 className="text-sm font-bold text-text mb-2">Executive Summary</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
              {[
                { label: 'Total Wells',         value: String(doc.executive_summary.total_wells) },
                { label: 'In Production',       value: String(doc.executive_summary.wells_in_production) },
                { label: 'In Injection',        value: String(doc.executive_summary.wells_in_injection) },
                { label: 'Active Faults',       value: String(doc.executive_summary.active_faults_count),     highlight: doc.executive_summary.active_faults_count > 0 ? 'text-red-400' : 'text-green-400' },
                { label: 'Critical Rod',        value: String(doc.executive_summary.critical_rod_fatigue_count), highlight: doc.executive_summary.critical_rod_fatigue_count > 0 ? 'text-red-400' : 'text-green-400' },
                { label: 'High Viscosity',      value: String(doc.executive_summary.high_viscosity_wells_count), highlight: doc.executive_summary.high_viscosity_wells_count > 0 ? 'text-amber-400' : 'text-green-400' },
                { label: 'Field Oil Rate (m³/d)', value: doc.executive_summary.total_field_oil_rate_m3d.toFixed(2) },
              ].map(({ label, value, highlight }) => (
                <div key={label} className="card-sm">
                  <p className="kpi-label mb-0.5 text-[9px]">{label}</p>
                  <p className={clsx('text-base font-bold tabular-nums', highlight ?? 'text-text')}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Priority actions */}
          <div>
            <h3 className="text-sm font-bold text-text mb-2">
              Priority Actions for Incoming Shift
              {doc.priority_actions.length === 0 && <span className="text-xs text-green-400 ml-2 font-normal">✓ No immediate actions</span>}
            </h3>
            {doc.priority_actions.length > 0 && (
              <div className="space-y-2">
                {doc.priority_actions.map((a, i) => (
                  <div key={i} className={clsx(
                    'px-3 py-2 rounded border text-xs flex gap-3',
                    PRIORITY_COLORS[a.priority] ?? PRIORITY_COLORS.info
                  )}>
                    <div className="shrink-0 flex flex-col items-center gap-0.5 pt-0.5">
                      <span className="font-bold uppercase text-[10px]">{a.priority}</span>
                      <span className="text-[9px] opacity-70">{a.well_id}</span>
                    </div>
                    <p className="flex-1">{a.action}</p>
                    <span className="text-[9px] opacity-60 self-start shrink-0">{a.source}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active faults */}
          {doc.active_faults.length > 0 && (
            <div>
              <h3 className="text-sm font-bold text-red-400 mb-2">⚠ Active Faults</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted">
                      <th className="py-1 px-2 text-left">Well</th>
                      <th className="py-1 px-2 text-left">Fault</th>
                      <th className="py-1 px-2 text-right">Severity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.active_faults.map(f => (
                      <tr key={f.well_id} className="border-b border-border/40 bg-red-900/10">
                        <td className="py-1.5 px-2 font-bold text-red-400">{f.well_id}</td>
                        <td className="py-1.5 px-2">{f.fault.replace(/_/g, ' ')}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{(f.severity * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Rod fatigue summary */}
          {(doc.rod_fatigue_summary.critical.length > 0 || doc.rod_fatigue_summary.high.length > 0) && (
            <div>
              <h3 className="text-sm font-bold text-text mb-2">
                Rod Fatigue Alerts
                <span className="text-xs text-muted font-normal ml-2">
                  ({doc.rod_fatigue_summary.total_wells_tracked} wells tracked)
                </span>
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {doc.rod_fatigue_summary.critical.map(r => (
                  <div key={r.well_id} className="card border-red-700/50 bg-red-900/10 text-xs">
                    <span className="font-bold text-red-400">⛔ {r.well_id}</span>
                    <span className="text-muted ml-2">D = {r.damage_pct.toFixed(1)}%</span>
                    <p className="text-muted mt-0.5">{r.recommended_workover}</p>
                  </div>
                ))}
                {doc.rod_fatigue_summary.high.map(r => (
                  <div key={r.well_id} className="card border-amber-700/50 bg-amber-900/10 text-xs">
                    <span className="font-bold text-amber-400">⚠ {r.well_id}</span>
                    <span className="text-muted ml-2">D = {r.damage_pct.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Carbon + allocation summary tiles */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {doc.carbon_summary && (
              <div className="card">
                <h3 className="text-xs font-bold text-text mb-2">Carbon KPIs <ProvenanceBadge tag="LITERATURE_ASSUMPTION" className="ml-1" /></h3>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'CO₂/bbl',     value: `${doc.carbon_summary.field_co2_per_bbl_kg?.toFixed(2)} kg` },
                    { label: 'Δ vs Base',   value: `${(doc.carbon_summary.co2_delta_vs_baseline_pct ?? 0) >= 0 ? '+' : ''}${doc.carbon_summary.co2_delta_vs_baseline_pct?.toFixed(1)}%` },
                    { label: 'Total Cost',  value: `₹${((doc.carbon_summary.total_cost_inr ?? 0) / 1000).toFixed(1)}k` },
                    { label: 'Cost/bbl',    value: `₹${doc.carbon_summary.field_cost_per_bbl_inr?.toFixed(0)}` },
                  ].map(({ label, value }) => (
                    <div key={label} className="card-sm">
                      <p className="kpi-label text-[9px]">{label}</p>
                      <p className="text-sm font-bold text-text tabular-nums">{value}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {doc.allocation_summary && (
              <div className="card">
                <h3 className="text-xs font-bold text-text mb-2">Steam Allocation <ProvenanceBadge tag="OPTIMIZER_RECOMMENDATION" className="ml-1" /></h3>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'Budget',      value: `${doc.allocation_summary.budget_m3?.toFixed(0)} m³` },
                    { label: 'Allocated',   value: `${doc.allocation_summary.allocated_m3?.toFixed(0)} m³` },
                    { label: 'Oil Gain',    value: `+${doc.allocation_summary.expected_oil_gain_pct?.toFixed(1)}%` },
                    { label: 'Field SOR',   value: doc.allocation_summary.field_sor?.toFixed(2) },
                  ].map(({ label, value }) => (
                    <div key={label} className="card-sm">
                      <p className="kpi-label text-[9px]">{label}</p>
                      <p className="text-sm font-bold text-text tabular-nums">{value}</p>
                    </div>
                  ))}
                </div>
                {doc.allocation_summary.excluded_wells.length > 0 && (
                  <p className="text-[10px] text-red-400 mt-1">
                    Excluded: {doc.allocation_summary.excluded_wells.join(', ')}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Wells table */}
          <div className="card overflow-hidden">
            <h3 className="text-sm font-bold text-text mb-2">Well Status at Handover</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-muted">
                    <th className="py-1.5 px-2 text-left">Well</th>
                    <th className="py-1.5 px-2 text-left">Phase</th>
                    <th className="py-1.5 px-2 text-right">Oil (m³/d)</th>
                    <th className="py-1.5 px-2 text-right">T (°C)</th>
                    <th className="py-1.5 px-2 text-right">Visc (cP)</th>
                    <th className="py-1.5 px-2 text-right">SOR</th>
                    <th className="py-1.5 px-2 text-right">Pump Eff</th>
                    <th className="py-1.5 px-2 text-right">SPM</th>
                    <th className="py-1.5 px-2 text-left">Fault</th>
                  </tr>
                </thead>
                <tbody>
                  {doc.wells_summary.map(w => (
                    <tr key={w.well_id} className={clsx(
                      'border-b border-border/40',
                      w.active_fault ? 'bg-red-900/10' : 'hover:bg-surface/50',
                    )}>
                      <td className="py-1.5 px-2 font-bold text-text">{w.well_id}</td>
                      <td className={clsx('py-1.5 px-2 font-semibold', PHASE_COLOR[w.phase] ?? 'text-muted')}>
                        {w.phase}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{w.oil_rate_m3d.toFixed(3)}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{w.reservoir_temp_c.toFixed(1)}</td>
                      <td className={clsx('py-1.5 px-2 text-right tabular-nums',
                        w.oil_viscosity_cp > 800 ? 'text-red-400 font-bold' : 'text-text'
                      )}>{w.oil_viscosity_cp.toFixed(0)}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{w.sor.toFixed(2)}</td>
                      <td className={clsx('py-1.5 px-2 text-right tabular-nums',
                        w.pump_efficiency_pct < 50 ? 'text-amber-400' : 'text-text'
                      )}>{w.pump_efficiency_pct.toFixed(1)}%</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{w.spm.toFixed(1)}</td>
                      <td className={clsx('py-1.5 px-2', w.active_fault ? 'text-red-400 font-semibold' : 'text-muted')}>
                        {w.active_fault?.replace(/_/g, ' ') ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Footer */}
          <div className="text-[9px] text-muted/50 italic text-center pt-2 border-t border-border">
            {doc.disclaimer}
          </div>

        </div>
      )}

      {/* Empty state */}
      {!doc && !loading && !error && (
        <div className="card text-center py-12 text-muted text-sm">
          <p className="text-2xl mb-2">📋</p>
          <p>Set shift details above and click <strong>Generate Handover</strong>.</p>
          <p className="text-xs mt-1 text-muted/60">
            Pulls live data from all system components: faults, rod fatigue, allocation, carbon.
          </p>
        </div>
      )}
    </div>
  )
}
