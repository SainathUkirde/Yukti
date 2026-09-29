/* src/hooks/useWellStream.ts
 * WebSocket hook — connects to /ws/stream/{well_id} and feeds Zustand store.
 */
import { useEffect, useRef, useCallback } from 'react'
import { useStore } from '@/store/useStore'
import type { WellState } from '@/types/well'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const WS_BASE = (import.meta as any).env?.VITE_WS_URL ?? `ws://${window.location.hostname}:8000`

export function useWellStream(wellId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const { updateWellState, appendHistoryTick, setConnected, addAlert } = useStore()

  const connect = useCallback(() => {
    if (!wellId) return
    if (wsRef.current) {
      wsRef.current.close()
    }
    const url = `${WS_BASE}/ws/stream/${wellId}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
    }

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'tick') {
          const state: WellState = msg.data
          updateWellState(state)
          // Append to history (lightweight version)
          appendHistoryTick({
            tick: state.tick,
            sim_time_days: state.sim_time_days,
            phase: state.phase,
            reservoir_temp_c: state.reservoir_temp_c.value,
            oil_rate_m3d: state.oil_rate_m3d.value,
            oil_viscosity_cp: state.oil_viscosity_cp.value,
            spm: state.spm.value,
            pump_efficiency_fraction: state.pump_efficiency_fraction.value,
            motor_power_kw: state.motor_power_kw.value,
            rod_float_risk_score: state.rod_float_risk_score.value,
            sor: state.sor.value,
            active_fault: state.active_fault,
          })
          // Alert on critical faults
          if (state.active_fault && state.fault_severity > 0.5) {
            addAlert(`${wellId}: ${state.active_fault.replace('_', ' ')} detected (severity ${(state.fault_severity * 100).toFixed(0)}%)`)
          }
        }
      } catch (e) {
        console.error('WS parse error', e)
      }
    }

    ws.onerror = () => {
      setConnected(false)
    }

    ws.onclose = () => {
      setConnected(false)
      // Reconnect after 3s
      setTimeout(() => {
        if (wsRef.current === ws) connect()
      }, 3000)
    }
  }, [wellId, updateWellState, appendHistoryTick, setConnected, addAlert])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])
}
