/* src/hooks/useFleetStream.ts
 * WebSocket hook — connects to /ws/fleet for multi-well overview grid updates.
 */
import { useEffect, useRef } from 'react'
import { useStore } from '@/store/useStore'
import type { WellSummary } from '@/types/well'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const getWsBase = () => {
  const envUrl = (import.meta as any).env?.VITE_WS_URL
  if (envUrl) return envUrl
  if (typeof window !== 'undefined') {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}`
  }
  return 'ws://localhost:8000'
}

export function useFleetStream() {
  const wsRef = useRef<WebSocket | null>(null)
  const { setAllWells } = useStore()

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(`${getWsBase()}/ws/fleet`)
      wsRef.current = ws

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'fleet') {
            setAllWells(msg.wells as WellSummary[])
          }
        } catch (e) {
          console.error('Fleet WS parse error', e)
        }
      }

      ws.onclose = () => {
        setTimeout(connect, 3000)
      }
    }
    connect()
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [setAllWells])
}
