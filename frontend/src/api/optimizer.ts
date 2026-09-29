/* src/api/optimizer.ts
 * Optimizer, What-If, Predictions, Recommendations API calls.
 */
import { api } from './client'
import type { OptimizationResult, WhatIfResult, Recommendation, PredictionResult } from '@/types/optimization'

export const optimizerApi = {
  optimize: (wellId: string, nTrials = 60, objective = 'min_cost_per_bbl', apply = false) =>
    api.post<OptimizationResult>('/optimize/', { well_id: wellId, n_trials: nTrials, objective, apply }),

  lastResult: (wellId: string) =>
    api.get<OptimizationResult>(`/optimize/${wellId}/last`),

  whatif: (wellId: string, overrides: Record<string, number | undefined>, tProdDays = 15) =>
    api.post<WhatIfResult>('/whatif/', { well_id: wellId, ...overrides, t_production_days: tProdDays }),

  predict: (wellId: string) =>
    api.post<PredictionResult>(`/predict/?well_id=${wellId}`, {}),

  riskScore: (wellId: string) =>
    api.get<{ risk_score: number; risk_level: string; top_factors: unknown[] }>(`/predict/${wellId}/risk`),

  recommendations: (wellId?: string, priority?: string) => {
    const params = new URLSearchParams()
    if (wellId) params.set('well_id', wellId)
    if (priority) params.set('priority', priority)
    return api.get<{ recommendations: Recommendation[]; count: number; critical_count: number }>(
      `/recommendations/?${params.toString()}`
    )
  },
}

export const assistantApi = {
  ask: (query: string, wellId?: string) =>
    api.post<{ answer: string; provenance: string; disclaimer: string }>('/assistant/', {
      query,
      well_id: wellId,
      include_well_context: !!wellId,
    }),

  topics: () =>
    api.get<{ topics: string[] }>('/assistant/topics'),
}

export const reportApi = {
  downloadUrl: (wellId: string) => `/api/report/${wellId}`,

  json: (wellId: string) =>
    api.get<{ well_state: unknown; optimizer_recommendation: unknown }>(`/report/${wellId}/json`),
}
