/* src/types/optimization.ts
 * Types for optimizer, what-if, and recommendation results.
 */

export interface OptimizationResult {
  well_id: string
  status: string
  elapsed_s: number
  n_trials: number
  objective: string
  method: string
  recommended_config: Record<string, number>
  best_css: Record<string, number>
  best_srp: Record<string, number>
  predicted_kpis: {
    oil_rate_m3d: number
    sor: number
    kwh_per_bbl: number
    pump_efficiency: number
    rod_float_risk: number
    cost_per_bbl_inr: number
  }
  baseline_kpis: {
    oil_rate_m3d: number
    sor: number
    kwh_per_bbl: number
    pump_efficiency: number
    rod_float_risk: number
    cost_per_bbl_inr: number
  }
  kpi_deltas: {
    oil_rate_delta_pct: number
    sor_delta_pct: number
    energy_delta_pct: number
    cost_per_bbl_delta_pct: number
    rod_risk_delta_pts: number
    steam_tonnes_saved_per_cycle: number
  }
  constraints_passed: boolean
  constraint_violations: Array<{
    constraint_id: string
    name: string
    severity: string
  }>
  best_trial_value: number
  applied: boolean
  provenance: string
}

export interface WhatIfResult {
  well_id: string
  overrides_applied: Record<string, number>
  t_production_days: number
  baseline: {
    reservoir_temp_c: number
    viscosity_cp: number
    oil_rate_m3d: number
    pump_fillage: number
    pump_efficiency: number
    sor: number
    kwh_per_bbl: number
    rod_float_risk: number
    motor_power_kw: number
  }
  projected: {
    reservoir_temp_c: number
    viscosity_cp: number
    oil_rate_m3d: number
    pump_fillage: number
    pump_efficiency: number
    sor: number
    kwh_per_bbl: number
    rod_float_risk: number
    motor_power_kw: number
  }
  deltas: {
    reservoir_temp_c: number
    viscosity_pct: number
    oil_rate_pct: number
    pump_fillage_pct: number
    pump_efficiency_pct: number
    sor_pct: number
    kwh_per_bbl_pct: number
    rod_float_risk: number
  }
  narrative: string[]
  constraint_violations: Array<Record<string, unknown>>
  constraints_passed: boolean
  rod_floating_risk_after: boolean
  provenance: string
}

export interface Recommendation {
  id: string
  well_id: string
  priority: 'critical' | 'high' | 'medium' | 'info'
  category: string
  title: string
  action: string
  rationale: string
  kpi_impact: Record<string, number>
  provenance: string
}

export interface PredictionResult {
  well_id: string
  fault_classification: {
    predicted_fault: string
    confidence: number
    class_probabilities: Record<string, number>
    top_features: Array<{ feature: string; importance: number }>
    provenance: string
  }
  failure_risk: {
    risk_score: number
    risk_level: 'low' | 'medium' | 'high'
    top_factors: Array<{ feature: string; importance: number }>
    provenance: string
  }
  production_forecast: {
    forecasts: Record<string, Record<string, number>>
    horizon_days: number
    provenance: string
  }
}
