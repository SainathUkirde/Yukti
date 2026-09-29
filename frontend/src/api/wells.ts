/* src/api/wells.ts
 * Well API calls.
 */
import { api } from './client'
import type { WellState, WellSummary, HistoryTick } from '@/types/well'

export const wellsApi = {
  list: () =>
    api.get<{ wells: WellSummary[]; count: number }>('/wells/'),

  get: (id: string) =>
    api.get<WellState>(`/wells/${id}`),

  history: (id: string, n = 100) =>
    api.get<{ well_id: string; ticks: HistoryTick[]; count: number }>(`/wells/${id}/history?n=${n}`),

  params: (id: string) =>
    api.get<Record<string, unknown>>(`/wells/${id}/params`),
}

export const cyclesApi = {
  list: (wellId?: string) =>
    api.get<{ cycles: unknown[]; count: number }>(wellId ? `/cycles/?well_id=${wellId}` : '/cycles/'),

  latestCycle: (wellId: string) =>
    api.get<Record<string, unknown>>(`/cycles/${wellId}/latest`),
}

export const faultsApi = {
  inject: (wellId: string, faultType: string, rampTicks = 30) =>
    api.post<{ status: string }>('/faults/inject', { well_id: wellId, fault_type: faultType, ramp_ticks: rampTicks }),

  resolve: (wellId: string, faultType?: string) =>
    api.post<{ status: string }>('/faults/resolve', { well_id: wellId, fault_type: faultType }),

  types: () =>
    api.get<{ fault_types: Array<{ id: string; description: string }> }>('/faults/types'),
}
