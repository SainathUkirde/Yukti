/* src/types/well.ts
 * TypeScript types for well state, config, and summaries.
 * Mirrors backend Pydantic schemas.
 */
import type { ProvenancedFloat, ProvenanceTag } from './provenance'

export interface WellConfig {
  well_id: string
  spm: number
  stroke_length_m: number
  vfd_frequency_hz: number
  steam_volume_cwe_m3: number
  soak_days: number
}

export interface WellState {
  well_id: string
  timestamp: string
  tick: number
  sim_time_days: number
  cycle_number: number
  phase: 'injection' | 'soak' | 'production' | 'idle'
  time_in_phase_days: number

  // Reservoir
  reservoir_temp_c: ProvenancedFloat
  heated_zone_radius_m: ProvenancedFloat
  reservoir_pressure_kpa: ProvenancedFloat
  oil_viscosity_cp: ProvenancedFloat
  T_peak_c: ProvenancedFloat

  // Production
  oil_rate_m3d: ProvenancedFloat
  water_rate_m3d: ProvenancedFloat
  water_cut_fraction: ProvenancedFloat
  cum_oil_m3: ProvenancedFloat
  cum_water_m3: ProvenancedFloat
  sor: ProvenancedFloat

  // SRP
  spm: ProvenancedFloat
  stroke_length_m: ProvenancedFloat
  vfd_frequency_hz: ProvenancedFloat
  peak_load_kn: ProvenancedFloat
  min_load_kn: ProvenancedFloat
  pump_fillage_fraction: ProvenancedFloat
  pump_efficiency_fraction: ProvenancedFloat
  motor_power_kw: ProvenancedFloat
  kwh_per_bbl: ProvenancedFloat

  // Risk
  rod_float_risk_ratio: ProvenancedFloat
  rod_float_risk_score: ProvenancedFloat
  goodman_ratio: ProvenancedFloat

  // Faults
  active_fault: string | null
  fault_severity: number
  active_alerts: string[]

  // Dyno card
  surface_position_m: number[]
  surface_load_kn: number[]
  downhole_position_m: number[]
  downhole_load_kn: number[]

  twin_sensor_deviation_pct: ProvenancedFloat
  config: WellConfig
  provenance: ProvenanceTag
}

export interface WellSummary {
  well_id: string
  well_name: string
  phase: string
  oil_rate_m3d: number
  reservoir_temp_c: number
  rod_failure_risk_score: number
  active_fault: string | null
  status_color: 'green' | 'amber' | 'red'
  cycle_number: number
  provenance: ProvenanceTag
}

export interface HistoryTick {
  tick: number
  sim_time_days: number
  phase: string
  reservoir_temp_c: number
  oil_rate_m3d: number
  oil_viscosity_cp: number
  spm: number
  pump_efficiency_fraction: number
  motor_power_kw: number
  rod_float_risk_score: number
  sor: number
  active_fault: string | null
}
