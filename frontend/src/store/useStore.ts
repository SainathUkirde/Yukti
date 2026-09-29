/* src/store/useStore.ts
 * Global Zustand store — central state for all live data.
 */
import { create } from 'zustand'
import type { WellState, WellSummary, HistoryTick } from '@/types/well'
import type { Recommendation, OptimizationResult, WhatIfResult, PredictionResult } from '@/types/optimization'

interface AppState {
  // Connection
  connected: boolean
  setConnected: (v: boolean) => void

  // Wells
  allWells: WellSummary[]
  setAllWells: (wells: WellSummary[]) => void

  // Selected well
  selectedWellId: string | null
  selectWell: (id: string | null) => void

  // Live well state (per well, latest tick)
  wellStates: Record<string, WellState>
  updateWellState: (state: WellState) => void

  // History ticks per well
  wellHistory: Record<string, HistoryTick[]>
  setWellHistory: (wellId: string, ticks: HistoryTick[]) => void
  appendHistoryTick: (tick: HistoryTick) => void

  // Predictions
  predictions: Record<string, PredictionResult>
  setPrediction: (wellId: string, result: PredictionResult) => void

  // Optimizer
  optimizationResults: Record<string, OptimizationResult>
  setOptimizationResult: (wellId: string, result: OptimizationResult) => void
  optimizing: boolean
  setOptimizing: (v: boolean) => void

  // What-If
  whatIfResult: WhatIfResult | null
  setWhatIfResult: (r: WhatIfResult | null) => void
  whatIfPending: boolean
  setWhatIfPending: (v: boolean) => void

  // Recommendations
  recommendations: Recommendation[]
  setRecommendations: (recs: Recommendation[]) => void

  // Alerts (active faults / critical recs)
  alerts: string[]
  addAlert: (msg: string) => void
  clearAlerts: () => void

  // UI state
  activePanel: 'kpi' | 'dyno' | 'optimizer' | 'whatif' | 'assistant' | 'alerts'
  setActivePanel: (p: AppState['activePanel']) => void
  darkMode: boolean
}

export const useStore = create<AppState>((set) => ({
  connected: false,
  setConnected: (v) => set({ connected: v }),

  allWells: [],
  setAllWells: (wells) => set({ allWells: wells }),

  selectedWellId: null,
  selectWell: (id) => set({ selectedWellId: id }),

  wellStates: {},
  updateWellState: (state) =>
    set((s) => ({ wellStates: { ...s.wellStates, [state.well_id]: state } })),

  wellHistory: {},
  setWellHistory: (wellId, ticks) =>
    set((s) => ({ wellHistory: { ...s.wellHistory, [wellId]: ticks } })),
  appendHistoryTick: (tick) =>
    set((s) => {
      const id = s.selectedWellId
      if (!id) return s
      const prev = s.wellHistory[id] ?? []
      const next = [...prev, tick].slice(-200)
      return { wellHistory: { ...s.wellHistory, [id]: next } }
    }),

  predictions: {},
  setPrediction: (wellId, result) =>
    set((s) => ({ predictions: { ...s.predictions, [wellId]: result } })),

  optimizationResults: {},
  setOptimizationResult: (wellId, result) =>
    set((s) => ({ optimizationResults: { ...s.optimizationResults, [wellId]: result } })),
  optimizing: false,
  setOptimizing: (v) => set({ optimizing: v }),

  whatIfResult: null,
  setWhatIfResult: (r) => set({ whatIfResult: r }),
  whatIfPending: false,
  setWhatIfPending: (v) => set({ whatIfPending: v }),

  recommendations: [],
  setRecommendations: (recs) => set({ recommendations: recs }),

  alerts: [],
  addAlert: (msg) => set((s) => ({ alerts: [msg, ...s.alerts].slice(0, 50) })),
  clearAlerts: () => set({ alerts: [] }),

  activePanel: 'kpi',
  setActivePanel: (p) => set({ activePanel: p }),
  darkMode: true,
}))
