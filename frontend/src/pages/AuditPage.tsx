/* src/pages/AuditPage.tsx
 * Feature 4 — Trust Layer: Audit Log, Approval Flow, Safe-Mode
 *
 * Shows:
 *  - Role switcher (demo — not real auth)
 *  - Safe-mode toggle
 *  - Pending recommendations with Approve/Reject/Apply buttons
 *  - Append-only audit log table with hash-chain verify
 *  - CSV export
 */
import { useEffect, useState, useCallback } from 'react'
import { auditApi } from '@/api/features'
import type { AuditEntry, RecState } from '@/api/features'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import clsx from 'clsx'

const ROLES = ['Viewer', 'Operator', 'Engineer'] as const
type Role = typeof ROLES[number]

const VERDICT_COLORS: Record<string, string> = {
  SAFE:    'text-green-400 bg-green-900/30 border-green-700/40',
  CAUTION: 'text-amber-400 bg-amber-900/30 border-amber-700/40',
  UNSAFE:  'text-red-400 bg-red-900/30 border-red-700/40',
}

const ACTION_COLORS: Record<string, string> = {
  proposed: 'text-blue-400',
  approved: 'text-green-400',
  rejected: 'text-red-400',
  applied:  'text-purple-400',
}

const STATE_COLORS: Record<string, string> = {
  proposed: 'border-blue-700/50 bg-blue-900/20',
  approved: 'border-green-700/50 bg-green-900/20',
  rejected: 'border-red-700/50 bg-red-900/20',
  applied:  'border-purple-700/50 bg-purple-900/20',
}

function exportCSV(entries: AuditEntry[]) {
  const cols = ['id','timestamp','well_id','role','recommendation_id','action',
                'constraint_result','approver','reason','entry_hash']
  const rows = entries.map(e => cols.map(c => JSON.stringify((e as unknown as Record<string,unknown>)[c] ?? '')).join(','))
  const csv = [cols.join(','), ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'audit_log.csv'; a.click()
}

export default function AuditPage() {
  const [status, setStatus] = useState<{
    current_role: string; safe_mode_active: boolean
    permissions: { can_approve: boolean; can_apply: boolean }
    total_audit_entries: number; pending_recommendations: number
  } | null>(null)
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [recStates, setRecStates] = useState<RecState[]>([])
  const [chainResult, setChainResult] = useState<{ valid: boolean; first_broken_at: number | null } | null>(null)
  const [loading, setLoading] = useState(false)
  const [approveInput, setApproveInput] = useState('')

  const reload = useCallback(async () => {
    const [s, l, rs] = await Promise.all([
      auditApi.status(),
      auditApi.log(undefined, undefined, 200),
      auditApi.listStates(),
    ])
    setStatus(s)
    setEntries(l.entries.slice().reverse()) // newest first
    setRecStates(rs.states)
  }, [])

  useEffect(() => { reload() }, [reload])

  const switchRole = async (role: string) => {
    await auditApi.setRole(role); reload()
  }

  const toggleSafeMode = async () => {
    if (!status) return
    await auditApi.setSafeMode(!status.safe_mode_active); reload()
  }

  const verifyChain = async () => {
    const r = await auditApi.verify(); setChainResult(r)
  }

  const handleApprove = async (recId: string) => {
    setLoading(true)
    try { await auditApi.approve(recId, approveInput || 'Engineer', '') }
    catch (e: unknown) { alert((e as Error).message) }
    finally { setLoading(false); reload() }
  }

  const handleReject = async (recId: string) => {
    setLoading(true)
    try { await auditApi.reject(recId, approveInput || 'Engineer', 'Rejected') }
    catch (e: unknown) { alert((e as Error).message) }
    finally { setLoading(false); reload() }
  }

  const handleApply = async (recId: string) => {
    setLoading(true)
    try { await auditApi.apply(recId, 'Operator') }
    catch (e: unknown) { alert((e as Error).message) }
    finally { setLoading(false); reload() }
  }

  return (
    <div className="p-4 space-y-4 max-w-6xl mx-auto">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-text">Trust Layer — Audit & Approval</h1>
        <ProvenanceBadge tag="DEMO_RESULT" />
        <span className="text-xs text-muted italic">
          Demo of human-in-the-loop controls — not real authentication
        </span>
      </div>

      {/* Status bar */}
      {status && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {/* Role switcher */}
          <div className="card-sm">
            <p className="kpi-label mb-1">Demo Role</p>
            <div className="flex gap-1">
              {ROLES.map(r => (
                <button key={r}
                  onClick={() => switchRole(r)}
                  className={clsx('text-xs px-2 py-0.5 rounded border transition-colors',
                    status.current_role === r
                      ? 'border-accent bg-accent/20 text-accent'
                      : 'border-border text-muted hover:border-accent/50'
                  )}
                >{r}</button>
              ))}
            </div>
            <p className="text-[9px] text-muted mt-1">
              Can approve: {status.permissions.can_approve ? '✓' : '✗'} |
              Can apply: {status.permissions.can_apply ? '✓' : '✗'}
            </p>
          </div>

          {/* Safe mode */}
          <div className="card-sm flex flex-col justify-between">
            <p className="kpi-label">Safe Mode</p>
            <div className="flex items-center gap-2 mt-1">
              <button onClick={toggleSafeMode}
                className={clsx('w-10 h-5 rounded-full transition-colors relative',
                  status.safe_mode_active ? 'bg-amber-500' : 'bg-border'
                )}>
                <span className={clsx('absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all',
                  status.safe_mode_active ? 'left-5' : 'left-0.5'
                )}/>
              </button>
              <span className={clsx('text-xs font-bold',
                status.safe_mode_active ? 'text-amber-400' : 'text-muted'
              )}>
                {status.safe_mode_active ? 'ON — steps clamped' : 'OFF'}
              </span>
            </div>
          </div>

          {/* Audit stats */}
          <div className="card-sm">
            <p className="kpi-label">Audit Entries</p>
            <p className="text-xl font-bold text-text">{status.total_audit_entries}</p>
            <p className="text-xs text-muted">{status.pending_recommendations} pending</p>
          </div>

          {/* Chain verify */}
          <div className="card-sm">
            <p className="kpi-label">Hash Chain</p>
            <button onClick={verifyChain} className="btn-secondary text-xs mt-1 w-full">Verify</button>
            {chainResult && (
              <p className={clsx('text-xs mt-1 font-bold',
                chainResult.valid ? 'text-green-400' : 'text-red-400'
              )}>
                {chainResult.valid ? '✓ Intact' : `✗ Broken at #${chainResult.first_broken_at}`}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Approver name input */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted">Approver name:</span>
        <input
          value={approveInput}
          onChange={e => setApproveInput(e.target.value)}
          placeholder="Your name"
          className="input text-xs w-40"
        />
      </div>

      {/* Pending recommendations */}
      {recStates.filter(s => s.state === 'proposed' || s.state === 'approved').length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-muted uppercase tracking-wide mb-2">
            Pending Recommendations
          </h2>
          <div className="space-y-2">
            {recStates
              .filter(s => s.state === 'proposed' || s.state === 'approved')
              .map(s => (
                <div key={s.recommendation_id}
                  className={clsx('border rounded-lg p-3', STATE_COLORS[s.state] ?? 'border-border bg-surface')}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-muted">{s.recommendation_id}</span>
                        <span className="text-xs text-muted">•</span>
                        <span className="text-xs text-muted">{s.well_id}</span>
                        <span className={clsx('text-[10px] px-1.5 py-0.5 rounded border', VERDICT_COLORS[s.verdict] ?? '')}>
                          {s.verdict}
                        </span>
                      </div>
                      {/* Confidence band */}
                      <p className="text-xs text-muted">
                        Confidence: [{s.confidence_low.toFixed(1)}%, +{s.confidence_high.toFixed(1)}%]
                      </p>
                    </div>
                    <div className="flex gap-1.5 flex-shrink-0">
                      {s.state === 'proposed' && (
                        <>
                          <button
                            onClick={() => handleApprove(s.recommendation_id)}
                            disabled={loading || !status?.permissions.can_approve}
                            className="btn-primary text-xs px-2"
                            title={!status?.permissions.can_approve ? 'Need Engineer role' : ''}
                          >
                            ✓ Approve
                          </button>
                          <button
                            onClick={() => handleReject(s.recommendation_id)}
                            disabled={loading}
                            className="btn-danger text-xs px-2"
                          >
                            ✗ Reject
                          </button>
                        </>
                      )}
                      {s.state === 'approved' && (
                        <button
                          onClick={() => handleApply(s.recommendation_id)}
                          disabled={loading || !status?.permissions.can_apply}
                          className="btn-primary text-xs px-2"
                        >
                          ▶ Apply
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Audit log table */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">
            Audit Log ({entries.length} entries)
          </h2>
          <button onClick={() => exportCSV(entries)} className="btn-secondary text-xs">
            ↓ Export CSV
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-border bg-surface">
                {['#','Time','Well','Role','Rec ID','Action','Verdict','Approver','Reason'].map(h => (
                  <th key={h} className="text-left px-2 py-1.5 text-muted font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-b border-border/40 hover:bg-surface/50">
                  <td className="px-2 py-1 font-mono text-muted">{e.id}</td>
                  <td className="px-2 py-1 text-muted whitespace-nowrap">
                    {new Date(e.timestamp).toLocaleTimeString()}
                  </td>
                  <td className="px-2 py-1 font-mono">{e.well_id}</td>
                  <td className="px-2 py-1 text-muted">{e.role}</td>
                  <td className="px-2 py-1 font-mono text-muted text-[9px] max-w-[120px] truncate">
                    {e.recommendation_id}
                  </td>
                  <td className={clsx('px-2 py-1 font-semibold', ACTION_COLORS[e.action] ?? 'text-muted')}>
                    {e.action}
                  </td>
                  <td className="px-2 py-1">
                    <span className={clsx('text-[9px] px-1 py-0.5 rounded border',
                      VERDICT_COLORS[e.constraint_result] ?? 'border-border text-muted'
                    )}>
                      {e.constraint_result}
                    </span>
                  </td>
                  <td className="px-2 py-1 text-muted">{e.approver}</td>
                  <td className="px-2 py-1 text-muted max-w-[150px] truncate">{e.reason}</td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr><td colSpan={9} className="text-center py-6 text-muted italic">No audit entries yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
