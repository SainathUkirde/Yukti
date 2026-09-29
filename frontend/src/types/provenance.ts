/* src/types/provenance.ts
 * Provenance system — every data point carries one of these 7 tags.
 * Colors match the Tailwind palette defined in tailwind.config.js
 */

export type ProvenanceTag =
  | 'FIELD_FACT'
  | 'LITERATURE_ASSUMPTION'
  | 'SYNTHETIC_HISTORICAL'
  | 'SIMULATED_LIVE'
  | 'ML_PREDICTION'
  | 'OPTIMIZER_RECOMMENDATION'
  | 'DEMO_RESULT'
  | 'USER_UPLOADED'

export interface ProvenancedFloat {
  value: number
  provenance: ProvenanceTag
  unit: string
  source?: string
}

export const PROVENANCE_COLORS: Record<ProvenanceTag, string> = {
  FIELD_FACT:               '#065f46',
  LITERATURE_ASSUMPTION:    '#1e40af',
  SYNTHETIC_HISTORICAL:     '#1a60b5',
  SIMULATED_LIVE:           '#1a7f37',
  ML_PREDICTION:            '#7c3aed',
  OPTIMIZER_RECOMMENDATION: '#c06c00',
  DEMO_RESULT:              '#b91c1c',
  USER_UPLOADED:            '#0d9488', // teal
}

export const PROVENANCE_BG: Record<ProvenanceTag, string> = {
  FIELD_FACT:               'bg-emerald-900/60 text-emerald-300',
  LITERATURE_ASSUMPTION:    'bg-blue-900/60 text-blue-300',
  SYNTHETIC_HISTORICAL:     'bg-blue-900/40 text-blue-400',
  SIMULATED_LIVE:           'bg-green-900/60 text-green-300',
  ML_PREDICTION:            'bg-purple-900/60 text-purple-300',
  OPTIMIZER_RECOMMENDATION: 'bg-amber-900/60 text-amber-300',
  DEMO_RESULT:              'bg-red-900/60 text-red-300',
  USER_UPLOADED:            'bg-teal-900/60 text-teal-300',
}

export const PROVENANCE_LABELS: Record<ProvenanceTag, string> = {
  FIELD_FACT:               'FIELD',
  LITERATURE_ASSUMPTION:    'LIT',
  SYNTHETIC_HISTORICAL:     'SYN-HIST',
  SIMULATED_LIVE:           'SIM-LIVE',
  ML_PREDICTION:            'ML',
  OPTIMIZER_RECOMMENDATION: 'OPT',
  DEMO_RESULT:              'DEMO',
  USER_UPLOADED:            'UPLOADED',
}
