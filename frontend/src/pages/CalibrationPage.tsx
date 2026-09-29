/* src/pages/CalibrationPage.tsx
 * Feature 3 — Data Upload & Calibration Wizard
 *
 * 4-step wizard:
 *  Step 1 — Choose target & download sample CSV template
 *  Step 2 — Upload CSV/Excel + map columns to required logical names
 *  Step 3 — Run SciPy curve_fit, show R², RMSE, fit curve chart
 *  Step 4 — Review & Activate: apply fitted params to live simulator
 *
 * Profile history panel shows all previously uploaded profiles.
 */
import { useState, useCallback, useRef } from 'react'
import ReactECharts from 'echarts-for-react'
import { calibrationApi, CalibrationProfile, ProfileDetail, FitResult } from '@/api/features'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'
import clsx from 'clsx'

// ── Constants ─────────────────────────────────────────────────────────────────
const TARGETS = [
  {
    id: 'viscosity_andrade',
    label: 'Viscosity–Temperature (Andrade)',
    description: 'Fit ln(μ) = A + B/T_K from lab measurements. Calibrates the Andrade viscosity model used by all simulations.',
    requiredCols: ['temperature_c', 'viscosity_cp'],
    optionalCols: ['well_id', 'date', 'source'],
  },
  {
    id: 'ipr_vogel',
    label: 'IPR Curve (Vogel)',
    description: 'Fit q = q_max·(1 − 0.2·Pwf/Pr − 0.8·(Pwf/Pr)²) from well tests. Updates the productivity index.',
    requiredCols: ['pwf_kpa', 'oil_rate_m3d'],
    optionalCols: ['well_id', 'date', 'reservoir_pressure_kpa'],
  },
]

const STEPS = ['Choose Target', 'Upload & Map', 'Calibrate', 'Review & Activate']

// ── Fit curve chart ───────────────────────────────────────────────────────────
function FitCurveChart({ fit, target }: { fit: FitResult; target: string }) {
  const isVisc = target === 'viscosity_andrade'

  // Build measured vs predicted scatter
  const n = fit.predicted.length
  const xLabel = isVisc ? 'Point index' : 'Point index'

  const option = {
    backgroundColor: 'transparent',
    grid: { top: 24, right: 16, bottom: 32, left: 56 },
    legend: {
      data: ['Measured', 'Predicted', 'Residual'],
      textStyle: { color: '#8b949e', fontSize: 9 },
      top: 2,
    },
    xAxis: {
      type: 'category',
      data: Array.from({ length: n }, (_, i) => String(i + 1)),
      name: xLabel,
      nameTextStyle: { color: '#8b949e', fontSize: 9 },
      axisLabel: { color: '#8b949e', fontSize: 9 },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    yAxis: [
      {
        type: 'value',
        name: isVisc ? 'Visc (cP)' : 'q (m³/d)',
        nameTextStyle: { color: '#8b949e', fontSize: 9 },
        axisLabel: { color: '#8b949e', fontSize: 9 },
        splitLine: { lineStyle: { color: '#30363d', type: 'dashed' } },
      },
      {
        type: 'value',
        name: 'Residual',
        nameTextStyle: { color: '#8b949e', fontSize: 9 },
        axisLabel: { color: '#8b949e', fontSize: 9 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Measured',
        type: 'scatter',
        data: fit.predicted.map((p, i) => [i + 1, +(p + fit.residuals[i]).toFixed(5)]),
        itemStyle: { color: '#3fb950' },
        symbolSize: 7,
      },
      {
        name: 'Predicted',
        type: 'line',
        data: fit.predicted.map((p, i) => [i + 1, +p.toFixed(5)]),
        lineStyle: { color: '#388bfd', width: 2 },
        symbol: 'none',
        smooth: true,
      },
      {
        name: 'Residual',
        type: 'bar',
        yAxisIndex: 1,
        data: fit.residuals.map((r, i) => [i + 1, +r.toFixed(6)]),
        itemStyle: { color: 'rgba(248,81,73,0.5)' },
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
    <ReactECharts option={option} style={{ height: 200, width: '100%' }} opts={{ renderer: 'canvas' }} />
  )
}

// ── Profile history row ───────────────────────────────────────────────────────
function ProfileRow({ p, onLoad }: { p: CalibrationProfile; onLoad: (id: string) => void }) {
  const targetInfo = TARGETS.find(t => t.id === p.calibration_target)
  return (
    <div className={clsx(
      'flex items-center justify-between px-3 py-2 rounded border text-xs',
      p.active
        ? 'border-accent/50 bg-accent/5 text-text'
        : 'border-border bg-surface/30 text-muted',
    )}>
      <div className="space-y-0.5">
        <div className="flex items-center gap-2">
          <span className="font-bold text-text">{p.profile_id}</span>
          {p.active && <span className="text-[10px] text-accent font-semibold uppercase">● Active</span>}
        </div>
        <div className="text-[10px]">{targetInfo?.label ?? p.calibration_target} · {p.n_rows} rows · {p.filename}</div>
        {p.fit_summary && (
          <div className="text-[10px] text-green-400">
            R² = {p.fit_summary.r_squared.toFixed(4)}
          </div>
        )}
      </div>
      <button onClick={() => onLoad(p.profile_id)} className="btn-secondary text-[10px] ml-4">
        Load
      </button>
    </div>
  )
}

// ── Main wizard ───────────────────────────────────────────────────────────────
export default function CalibrationPage() {
  const [step, setStep]               = useState(0)
  const [target, setTarget]           = useState(TARGETS[0].id)
  const [file, setFile]               = useState<File | null>(null)
  const [columnMap, setColumnMap]     = useState<Record<string, string>>({})
  const [csvHeaders, setCsvHeaders]   = useState<string[]>([])
  const [profile, setProfile]         = useState<CalibrationProfile | null>(null)
  const [detail, setDetail]           = useState<ProfileDetail | null>(null)
  const [profiles, setProfiles]       = useState<CalibrationProfile[]>([])
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState<string | null>(null)
  const [activateResult, setActivateResult] = useState<Record<string, number> | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const targetInfo = TARGETS.find(t => t.id === target)!

  // ── Step helpers ────────────────────────────────────────────────────────────

  const downloadSample = useCallback(async () => {
    try {
      const csv = await calibrationApi.getSample(target)
      const blob = new Blob([csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `sample_${target}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(String(e))
    }
  }, [target])

  const onFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    setError(null)

    // Parse CSV headers for column mapping
    const reader = new FileReader()
    reader.onload = ev => {
      const text = ev.target?.result as string
      const firstLine = text.split('\n')[0]
      const headers = firstLine.split(',').map(h => h.trim().replace(/"/g, ''))
      setCsvHeaders(headers)

      // Auto-map columns that have identical names
      const auto: Record<string, string> = {}
      for (const logCol of targetInfo.requiredCols) {
        if (headers.includes(logCol)) auto[logCol] = logCol
      }
      setColumnMap(auto)
    }
    reader.readAsText(f)
  }, [targetInfo])

  const doUpload = useCallback(async () => {
    if (!file) return
    const missing = targetInfo.requiredCols.filter(c => !columnMap[c])
    if (missing.length > 0) {
      setError(`Please map all required columns: ${missing.join(', ')}`)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const p = await calibrationApi.upload(file, target, columnMap)
      setProfile(p)
      setStep(2)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [file, target, columnMap, targetInfo])

  const doCalibrate = useCallback(async () => {
    if (!profile) return
    setLoading(true)
    setError(null)
    try {
      const d = await calibrationApi.calibrate(profile.profile_id)
      setDetail(d)
      setStep(3)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [profile])

  const doActivate = useCallback(async () => {
    if (!detail) return
    setLoading(true)
    setError(null)
    try {
      const r = await calibrationApi.activate(detail.profile_id)
      setActivateResult(r.applied_params)
      setDetail({ ...detail, active: true })
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [detail])

  const loadProfiles = useCallback(async () => {
    try {
      const r = await calibrationApi.listProfiles()
      setProfiles(r.profiles)
    } catch {/* ignore */}
  }, [])

  const loadProfile = useCallback(async (pid: string) => {
    setLoading(true)
    try {
      const d = await calibrationApi.getProfile(pid)
      setDetail(d)
      setProfile(d)
      setTarget(d.calibration_target)
      setStep(d.calibrated ? 3 : 2)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  // Load profiles on mount
  useState(() => { loadProfiles() })

  // ── Render ──────────────────────────────────────────────────────────────────
  const fit = detail?.fit_result

  return (
    <div className="p-4 max-w-5xl mx-auto space-y-4">

      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-text">Calibration Wizard</h1>
        <ProvenanceBadge tag="USER_UPLOADED" />
        <ProvenanceBadge tag="CALIBRATED_MODEL" />
        <span className="text-xs text-muted italic">
          SciPy curve_fit · Andrade viscosity · Vogel IPR
        </span>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-0 overflow-x-auto">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center">
            <div className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold whitespace-nowrap cursor-pointer',
              i === step
                ? 'bg-accent/20 text-accent border border-accent/50'
                : i < step
                  ? 'text-green-400 cursor-pointer'
                  : 'text-muted cursor-not-allowed',
            )}
              onClick={() => i < step && setStep(i)}
            >
              <span className={clsx(
                'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold',
                i === step ? 'bg-accent text-bg' : i < step ? 'bg-green-500 text-bg' : 'bg-border text-muted',
              )}>
                {i < step ? '✓' : i + 1}
              </span>
              {s}
            </div>
            {i < STEPS.length - 1 && <span className="text-border mx-1 text-xs">→</span>}
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="card border-red-700/50 bg-red-900/20 text-red-400 text-xs px-3 py-2">
          {error}
        </div>
      )}

      {/* ── Step 0: Choose target ────────────────────────────────────────── */}
      {step === 0 && (
        <div className="card space-y-3">
          <h2 className="text-sm font-bold text-text">Step 1 — Choose Calibration Target</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {TARGETS.map(t => (
              <button
                key={t.id}
                onClick={() => setTarget(t.id)}
                className={clsx(
                  'text-left px-4 py-3 rounded border transition-all',
                  target === t.id
                    ? 'border-accent bg-accent/10 text-text'
                    : 'border-border bg-surface/30 text-muted hover:border-accent/50',
                )}
              >
                <p className="font-bold text-sm mb-1">{t.label}</p>
                <p className="text-xs">{t.description}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {t.requiredCols.map(c => (
                    <span key={c} className="px-1.5 py-0.5 rounded bg-surface text-[10px] text-accent border border-accent/30">
                      {c} *
                    </span>
                  ))}
                  {t.optionalCols.map(c => (
                    <span key={c} className="px-1.5 py-0.5 rounded bg-surface text-[10px] text-muted border border-border">
                      {c}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button onClick={downloadSample} className="btn-secondary text-xs">
              ⬇ Download Sample CSV
            </button>
            <span className="text-[10px] text-muted italic">
              Sample uses synthetic data (SYNTHETIC_HISTORICAL)
            </span>
            <button onClick={() => setStep(1)} className="btn-primary text-sm ml-auto px-4 py-1.5">
              Next →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 1: Upload & Map ─────────────────────────────────────────── */}
      {step === 1 && (
        <div className="card space-y-4">
          <h2 className="text-sm font-bold text-text">Step 2 — Upload File & Map Columns</h2>
          <p className="text-xs text-muted">
            Target: <strong className="text-text">{targetInfo.label}</strong>
          </p>

          {/* File input */}
          <div
            onClick={() => fileInputRef.current?.click()}
            className={clsx(
              'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors',
              file ? 'border-accent/50 bg-accent/5' : 'border-border hover:border-accent/40',
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={onFileChange}
            />
            {file ? (
              <div>
                <p className="text-text font-bold">{file.name}</p>
                <p className="text-xs text-muted">{(file.size / 1024).toFixed(1)} KB</p>
                {csvHeaders.length > 0 && (
                  <p className="text-xs text-accent mt-1">
                    {csvHeaders.length} columns detected: {csvHeaders.slice(0, 5).join(', ')}{csvHeaders.length > 5 ? '…' : ''}
                  </p>
                )}
              </div>
            ) : (
              <div>
                <p className="text-muted text-sm">Click to select CSV or Excel file</p>
                <p className="text-xs text-muted/60 mt-1">Max 5 MB · .csv .xlsx .xls</p>
              </div>
            )}
          </div>

          {/* Column mapping */}
          {csvHeaders.length > 0 && (
            <div>
              <p className="text-xs text-muted mb-2 font-semibold uppercase tracking-wide">
                Map required columns (* = required)
              </p>
              <div className="space-y-2">
                {targetInfo.requiredCols.map(logCol => (
                  <div key={logCol} className="flex items-center gap-3">
                    <span className="text-xs text-accent w-40 font-mono">{logCol} *</span>
                    <select
                      value={columnMap[logCol] ?? ''}
                      onChange={e => setColumnMap(prev => ({ ...prev, [logCol]: e.target.value }))}
                      className="flex-1 bg-surface border border-border rounded px-2 py-1 text-xs text-text"
                    >
                      <option value="">— select column —</option>
                      {csvHeaders.map(h => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                    <span className={clsx(
                      'text-[10px] font-semibold',
                      columnMap[logCol] ? 'text-green-400' : 'text-red-400',
                    )}>
                      {columnMap[logCol] ? '✓' : '✗'}
                    </span>
                  </div>
                ))}
                {targetInfo.optionalCols.map(logCol => (
                  <div key={logCol} className="flex items-center gap-3">
                    <span className="text-xs text-muted w-40 font-mono">{logCol}</span>
                    <select
                      value={columnMap[logCol] ?? ''}
                      onChange={e => setColumnMap(prev => ({ ...prev, [logCol]: e.target.value }))}
                      className="flex-1 bg-surface border border-border rounded px-2 py-1 text-xs text-muted"
                    >
                      <option value="">— optional —</option>
                      {csvHeaders.map(h => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-2 pt-1">
            <button onClick={() => setStep(0)} className="btn-secondary text-xs">← Back</button>
            <button
              onClick={doUpload}
              disabled={loading || !file}
              className="btn-primary text-sm ml-auto px-4 py-1.5"
            >
              {loading ? '⏳ Uploading…' : 'Upload & Continue →'}
            </button>
          </div>
        </div>
      )}

      {/* ── Step 2: Calibrate ────────────────────────────────────────────── */}
      {step === 2 && profile && (
        <div className="card space-y-3">
          <h2 className="text-sm font-bold text-text">Step 3 — Run Calibration</h2>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Profile ID',  value: profile.profile_id },
              { label: 'Target',      value: TARGETS.find(t => t.id === profile.calibration_target)?.label ?? profile.calibration_target },
              { label: 'Data Points', value: String(profile.n_rows) },
              { label: 'Provenance',  value: profile.provenance },
            ].map(({ label, value }) => (
              <div key={label} className="card-sm">
                <p className="kpi-label mb-0.5">{label}</p>
                <p className="text-xs font-bold text-text truncate">{value}</p>
              </div>
            ))}
          </div>

          <p className="text-xs text-muted italic">
            Will run SciPy <code>curve_fit</code> using the Levenberg-Marquardt algorithm.
            Output: fitted parameters + R² goodness-of-fit + per-point residuals.
          </p>

          <div className="flex gap-2 pt-1">
            <button onClick={() => setStep(1)} className="btn-secondary text-xs">← Back</button>
            <button
              onClick={doCalibrate}
              disabled={loading}
              className="btn-primary text-sm ml-auto px-4 py-1.5"
            >
              {loading ? '⏳ Fitting…' : '▶ Run Curve Fit →'}
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Review & Activate ────────────────────────────────────── */}
      {step === 3 && detail && fit && (
        <div className="space-y-3">

          {/* Fit quality banner */}
          <div className={clsx(
            'card border flex items-center gap-4 flex-wrap',
            fit.r_squared >= 0.95
              ? 'border-green-700/50 bg-green-900/10'
              : fit.r_squared >= 0.80
                ? 'border-amber-700/50 bg-amber-900/10'
                : 'border-red-700/50 bg-red-900/10',
          )}>
            <div>
              <p className="text-xs text-muted">Goodness of Fit</p>
              <p className={clsx(
                'text-2xl font-bold tabular-nums',
                fit.r_squared >= 0.95 ? 'text-green-400' : fit.r_squared >= 0.80 ? 'text-amber-400' : 'text-red-400',
              )}>
                R² = {fit.r_squared.toFixed(4)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Points Fitted</p>
              <p className="text-lg font-bold text-text">{fit.n_points}</p>
            </div>
            {fit.rmse_cp !== undefined && (
              <div>
                <p className="text-xs text-muted">RMSE (cP)</p>
                <p className="text-lg font-bold text-text tabular-nums">{fit.rmse_cp.toFixed(3)}</p>
              </div>
            )}
            {fit.rmse_m3d !== undefined && (
              <div>
                <p className="text-xs text-muted">RMSE (m³/d)</p>
                <p className="text-lg font-bold text-text tabular-nums">{fit.rmse_m3d.toFixed(5)}</p>
              </div>
            )}
            <ProvenanceBadge tag="CALIBRATED_MODEL" className="ml-auto" />
          </div>

          {/* Fitted parameters */}
          <div className="card">
            <h2 className="text-sm font-bold text-text mb-2">Fitted Parameters</h2>
            <p className="text-xs text-muted italic mb-3">{fit.equation}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-2">
              {Object.entries(fit.params).map(([k, v]) => (
                <div key={k} className="card-sm">
                  <p className="kpi-label mb-0.5 font-mono">{k}</p>
                  <p className="text-sm font-bold text-accent tabular-nums">{typeof v === 'number' ? v.toFixed(5) : v}</p>
                  {fit.param_std_err[k] !== undefined && (
                    <p className="text-[10px] text-muted mt-0.5">
                      ± {fit.param_std_err[k].toFixed(5)}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <p className="text-[10px] text-muted/60 italic">
              Reference: {fit.reference} · PROVENANCE: {fit.provenance}
            </p>
          </div>

          {/* Fit curve chart */}
          <div className="card">
            <h2 className="text-sm font-bold text-text mb-2">Measured vs Predicted + Residuals</h2>
            <FitCurveChart fit={fit} target={detail.calibration_target} />
          </div>

          {/* Activate */}
          {activateResult ? (
            <div className="card border-green-700/50 bg-green-900/10 space-y-2">
              <p className="text-sm font-bold text-green-400">✓ Profile Activated</p>
              <p className="text-xs text-muted">
                The following simulator constants have been updated in-memory:
              </p>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(activateResult).map(([k, v]) => (
                  <div key={k} className="card-sm">
                    <p className="kpi-label font-mono">{k}</p>
                    <p className="text-sm font-bold text-accent tabular-nums">{(v as number).toFixed(6)}</p>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-muted/50 italic">
                In-memory only. Restarting the process resets to file defaults.
                NOT validated against real Baghewala lab data.
              </p>
              <ProvenanceBadge tag="CALIBRATED_MODEL" />
            </div>
          ) : (
            <div className="card flex items-center justify-between flex-wrap gap-3">
              <div>
                <p className="text-sm font-bold text-text">Activate This Profile?</p>
                <p className="text-xs text-muted">
                  Updates the live simulator's {detail.calibration_target === 'viscosity_andrade' ? 'Andrade A/B constants' : 'PI reference value'} in-memory.
                </p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setStep(2)} className="btn-secondary text-xs">← Back</button>
                <button
                  onClick={doActivate}
                  disabled={loading}
                  className="btn-primary text-sm px-4 py-1.5"
                >
                  {loading ? '⏳ Activating…' : '✓ Activate Profile'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Profile history ───────────────────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-text">Profile History</h2>
          <button onClick={loadProfiles} className="btn-secondary text-xs">↻ Refresh</button>
        </div>
        {profiles.length === 0 ? (
          <p className="text-xs text-muted/60 italic">No profiles yet. Upload data above to start.</p>
        ) : (
          <div className="space-y-2">
            {profiles.map(p => (
              <ProfileRow key={p.profile_id} p={p} onLoad={loadProfile} />
            ))}
          </div>
        )}
      </div>

    </div>
  )
}
