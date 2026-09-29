/* src/api/features.ts
 * API calls for all 5 new features (Trust Layer, Rod Fatigue, Allocator, Calibration, Carbon).
 */
import { api } from './client'

// ── Feature 4: Trust Layer ────────────────────────────────────────────────────

export const auditApi = {
  status: () =>
    api.get<{
      current_role: string
      permissions: { can_approve: boolean; can_apply: boolean }
      safe_mode_active: boolean
      safe_mode_limits: Record<string, number>
      total_audit_entries: number
      pending_recommendations: number
      provenance: string
      disclaimer: string
    }>('/audit/status'),

  log: (wellId?: string, action?: string, limit = 100) => {
    const params = new URLSearchParams()
    if (wellId) params.set('well_id', wellId)
    if (action) params.set('action', action)
    params.set('limit', String(limit))
    return api.get<{ entries: AuditEntry[]; count: number; total: number }>(`/audit?${params}`)
  },

  verify: () =>
    api.get<{ valid: boolean; first_broken_at: number | null; total_entries: number }>('/audit/verify'),

  setRole: (role: string) =>
    api.post<{ role: string; permissions: Record<string, boolean> }>('/audit/role', { role }),

  setSafeMode: (active: boolean) =>
    api.post<{ safe_mode_active: boolean }>('/audit/safe-mode', { active }),

  listStates: (wellId?: string) => {
    const params = wellId ? `?well_id=${wellId}` : ''
    return api.get<{ states: RecState[] }>(`/audit/recommendations${params}`)
  },

  propose: (recId: string, wellId: string, recommendation: Record<string, unknown>,
            confidenceLow = 0, confidenceHigh = 0, constraintResult = 'SAFE') =>
    api.post<RecState>(`/recommendations/${recId}/propose`, {
      well_id: wellId, recommendation, confidence_low: confidenceLow,
      confidence_high: confidenceHigh, constraint_result: constraintResult,
    }),

  approve: (recId: string, approver: string, reason = '') =>
    api.post<RecState>(`/recommendations/${recId}/approve`, { approver, reason }),

  reject: (recId: string, approver: string, reason = '') =>
    api.post<RecState>(`/recommendations/${recId}/reject`, { approver, reason }),

  apply: (recId: string, approver = 'Operator') =>
    api.post<{ state: RecState; applied_config: Record<string, number>; sim_ok: boolean }>(
      `/recommendations/${recId}/apply`, { approver }
    ),

  getState: (recId: string) =>
    api.get<RecState>(`/recommendations/${recId}/state`),
}

export interface AuditEntry {
  id: number
  timestamp: string
  well_id: string
  role: string
  recommendation_id: string
  action: string
  before_values: Record<string, unknown>
  after_values: Record<string, unknown>
  constraint_result: string
  approver: string
  reason: string
  outcome_values: Record<string, unknown> | null
  entry_hash: string
  prev_hash: string
  provenance: string
}

// ── Feature 1: Steam Allocator ────────────────────────────────────────────────

export interface WellAllocation {
  well_id: string
  rank: number
  steam_volume_m3: number
  marginal_oil_per_m3_steam: number
  expected_oil_m3: number
  expected_sor: number
  expected_kwh_per_bbl: number
  start_day: number
  duration_days: number
  rod_fatigue_damage: number
  rod_life_constraint_applied: boolean
  rod_life_reason: string
  constraints_passed: boolean
  constraint_violations: Array<{ constraint_id: string; name: string; severity: string }>
  explanation: string
  provenance: string
}

export interface AllocationResult {
  well_allocations: WellAllocation[]
  baseline_allocations: WellAllocation[]
  total_steam_allocated_m3: number
  total_steam_budget_m3: number
  expected_total_oil_m3: number
  baseline_total_oil_m3: number
  oil_gain_vs_baseline_pct: number
  expected_field_sor: number
  period_days: number
  generator_capacity_m3_per_day: number
  wells_excluded_rod_fatigue: string[]
  method: string
  provenance: string
}

// ── Feature 3: Calibration Wizard ────────────────────────────────────────────

export interface CalibrationProfile {
  profile_id: string
  filename: string
  calibration_target: string
  n_rows: number
  uploaded_at: string
  calibrated: boolean
  active: boolean
  activated_at?: string | null
  fit_summary?: {
    model: string
    params: Record<string, number>
    r_squared: number
    n_points: number
    rmse_cp?: number
    rmse_m3d?: number
    provenance: string
  } | null
  provenance: string
}

export interface FitResult {
  model: string
  equation: string
  params: Record<string, number>
  param_std_err: Record<string, number>
  r_squared: number
  n_points: number
  rmse_cp?: number
  rmse_m3d?: number
  predicted: number[]
  residuals: number[]
  reference: string
  provenance: string
  temperature_c_range?: [number, number]
  viscosity_cp_range?: [number, number]
  pwf_kpa_range?: [number, number]
  q_range_m3d?: [number, number]
}

export interface ProfileDetail extends CalibrationProfile {
  fit_result: FitResult | null
}

export const calibrationApi = {
  getSample: (target: string) =>
    fetch(`/api/data/sample?target=${target}`).then(r => r.text()),

  upload: (file: File, target: string, columnMap: Record<string, string>) => {
    const form = new FormData()
    form.append('file', file)
    form.append('calibration_target', target)
    form.append('column_map_json', JSON.stringify(columnMap))
    return fetch('/api/data/upload', { method: 'POST', body: form })
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json() as Promise<CalibrationProfile>
      })
  },

  calibrate: (profileId: string) =>
    api.post<ProfileDetail>('/data/calibrate', { profile_id: profileId }),

  listProfiles: () =>
    api.get<{ profiles: CalibrationProfile[]; count: number; active_profiles: Record<string, string> }>('/data/profiles'),

  getProfile: (profileId: string) =>
    api.get<ProfileDetail>(`/data/profiles/${profileId}`),

  activate: (profileId: string) =>
    api.post<ProfileDetail & { applied_params: Record<string, number>; note: string }>(
      `/data/profiles/${profileId}/activate`, {}
    ),
}

export const allocatorApi = {
  allocate: (
    steamBudgetM3: number,
    generatorCapacityM3PerDay: number,
    periodDays: number,
    wellIds?: string[],
  ) =>
    api.post<AllocationResult>('/field/allocate', {
      steam_budget_m3: steamBudgetM3,
      generator_capacity_m3_per_day: generatorCapacityM3PerDay,
      period_days: periodDays,
      well_ids: wellIds ?? null,
    }),

  getSchedule: () => api.get<AllocationResult>('/field/schedule'),
}

// ── Feature 5: Carbon Tracker & Handover ──────────────────────────────────────

export interface WellCarbonReport {
  well_id: string
  period_days: number
  steam_volume_m3: number
  steam_energy_gj: number
  fuel_energy_gj: number
  motor_kwh: number
  co2_steam_t: number
  co2_elec_t: number
  co2_total_t: number
  co2_per_bbl_kg: number
  co2_delta_vs_baseline_pct: number
  gas_cost_inr: number
  elec_cost_inr: number
  total_cost_inr: number
  cost_per_bbl_inr: number
  cum_oil_m3: number
  cum_oil_bbl: number
  sor: number
  assumptions_used: Record<string, number>
  provenance: string
  disclaimer: string
}

export interface FieldCarbonReport {
  wells: WellCarbonReport[]
  field_totals: {
    total_co2_t: number
    total_oil_bbl: number
    total_cost_inr: number
    total_steam_m3: number
    total_motor_kwh: number
    field_co2_per_bbl_kg: number
    field_cost_per_bbl_inr: number
    co2_delta_vs_baseline_pct: number
    n_wells: number
  }
  provenance: string
  disclaimer: string
}

export interface CarbonAssumptions {
  boiler_efficiency: number
  emission_factor_gas_kg_per_gj: number
  grid_emission_factor_kg_per_kwh: number
  steam_density_kg_per_m3: number
  gas_price_inr_per_gj: number
  elec_price_inr_per_kwh: number
  cp_water_kj_per_kg_k: number
  steam_temp_c: number
  water_inlet_temp_c: number
  latent_heat_kj_per_kg: number
  provenance: string
  sources: string
}

export interface HandoverDoc {
  handover_id: string
  generated_at: string
  shift_label: string
  outgoing_operator: string
  incoming_operator: string
  executive_summary: {
    total_wells: number
    wells_in_production: number
    wells_in_injection: number
    active_faults_count: number
    critical_rod_fatigue_count: number
    high_viscosity_wells_count: number
    total_field_oil_rate_m3d: number
  }
  priority_actions: Array<{
    priority: string
    well_id: string
    action: string
    source: string
  }>
  active_faults: Array<{ well_id: string; fault: string; severity: number }>
  wells_summary: Array<{
    well_id: string
    phase: string
    cycle_number: number
    oil_rate_m3d: number
    reservoir_temp_c: number
    oil_viscosity_cp: number
    sor: number
    pump_efficiency_pct: number
    spm: number
    rod_float_risk: number
    active_fault: string | null
    alerts: string[]
    provenance: string
  }>
  rod_fatigue_summary: {
    critical: Array<{ well_id: string; damage_pct: number; recommended_workover: string }>
    high: Array<{ well_id: string; damage_pct: number }>
    total_wells_tracked: number
  }
  allocation_summary: {
    budget_m3: number
    allocated_m3: number
    expected_oil_gain_pct: number
    field_sor: number
    excluded_wells: string[]
    provenance: string
  } | null
  carbon_summary: {
    field_co2_per_bbl_kg: number
    co2_delta_vs_baseline_pct: number
    total_cost_inr: number
    field_cost_per_bbl_inr: number
    provenance: string
  } | null
  provenance: string
  disclaimer: string
}

export const carbonApi = {
  getWellCarbon: (wellId: string, periodDays = 1.0) =>
    api.get<WellCarbonReport>(`/wells/${wellId}/carbon?period_days=${periodDays}`),

  getFieldCarbon: (periodDays = 1.0) =>
    api.get<FieldCarbonReport>(`/field/carbon?period_days=${periodDays}`),

  getAssumptions: () => api.get<CarbonAssumptions>('/carbon/assumptions'),

  updateAssumptions: (updates: Partial<Record<string, number>>) =>
    api.put<CarbonAssumptions & { updated_keys: string[] }>('/carbon/assumptions', updates),

  getHandover: (shiftLabel = 'Day Shift', outgoing = 'Operator A', incoming = 'Operator B', periodDays = 1.0) => {
    const p = new URLSearchParams({
      shift_label: shiftLabel,
      outgoing_operator: outgoing,
      incoming_operator: incoming,
      period_days: String(periodDays),
    })
    return api.get<HandoverDoc>(`/handover?${p}`)
  },
}

export interface RecState {
  recommendation_id: string
  well_id: string
  state: string  // proposed | approved | rejected | applied
  verdict: string  // SAFE | CAUTION | UNSAFE
  confidence_low: number
  confidence_high: number
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
  approved_by: string | null
  safe_mode_active: boolean
  provenance: string
}
