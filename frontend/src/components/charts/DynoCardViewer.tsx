/* src/components/charts/DynoCardViewer.tsx
 * Renders live dynamometer card (surface + downhole) using ECharts.
 * Shows the iconic closed loop card shape — healthy vs fault patterns.
 */
import ReactECharts from 'echarts-for-react'
import { useStore } from '@/store/useStore'
import { useMemo } from 'react'
import { PhaseChip } from '@/components/ui/PhaseChip'

const FAULT_COLORS: Record<string, string> = {
  rod_floating:    '#f97316',
  pump_off:        '#ef4444',
  gas_interference:'#eab308',
  fluid_pound:     '#f85149',
  pump_unsetting:  '#a855f7',
}

export function DynoCardViewer() {
  const { wellStates, selectedWellId } = useStore()
  const state = selectedWellId ? wellStates[selectedWellId] : null

  const option = useMemo(() => {
    if (!state) return {}
    const surfX = state.surface_position_m
    const surfY = state.surface_load_kn
    const downX = state.downhole_position_m
    const downY = state.downhole_load_kn
    const faultColor = state.active_fault ? (FAULT_COLORS[state.active_fault] ?? '#f85149') : '#388bfd'
    const downColor  = state.active_fault ? (FAULT_COLORS[state.active_fault] ?? '#3fb950') : '#3fb950'

    return {
      backgroundColor: 'transparent',
      grid: { top: 30, right: 20, bottom: 30, left: 50 },
      xAxis: {
        type: 'value',
        name: 'Position (m)',
        nameTextStyle: { color: '#8b949e', fontSize: 9 },
        axisLabel: { color: '#8b949e', fontSize: 9 },
        axisLine: { lineStyle: { color: '#30363d' } },
        splitLine: { lineStyle: { color: '#30363d', type: 'dashed' } },
      },
      yAxis: {
        type: 'value',
        name: 'Load (kN)',
        nameTextStyle: { color: '#8b949e', fontSize: 9 },
        axisLabel: { color: '#8b949e', fontSize: 9 },
        axisLine: { lineStyle: { color: '#30363d' } },
        splitLine: { lineStyle: { color: '#30363d', type: 'dashed' } },
      },
      series: [
        {
          name: 'Surface',
          type: 'line',
          data: surfX.map((x, i) => [x, surfY[i]]),
          smooth: false,
          symbol: 'none',
          lineStyle: { color: faultColor, width: 2 },
          areaStyle: { color: `${faultColor}15` },
        },
        {
          name: 'Downhole',
          type: 'line',
          data: downX.map((x, i) => [x, downY[i]]),
          smooth: false,
          symbol: 'none',
          lineStyle: { color: downColor, width: 1.5, type: 'dashed' },
        },
      ],
      legend: {
        data: ['Surface', 'Downhole'],
        textStyle: { color: '#8b949e', fontSize: 9 },
        icon: 'circle',
        itemWidth: 8,
        top: 4,
        right: 8,
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        textStyle: { color: '#e6edf3', fontSize: 10 },
        formatter: (params: unknown[]) => {
          const p = (params as Array<{ value: number[] }>)[0]
          return p ? `pos: ${p.value[0].toFixed(2)}m<br/>load: ${p.value[1].toFixed(2)} kN` : ''
        },
      },
    }
  }, [state])

  if (!state) {
    return (
      <div className="card h-full flex items-center justify-center text-muted text-xs">
        Select a well
      </div>
    )
  }

  const isHealthy = !state.active_fault
  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted uppercase tracking-wide">Dyno Card</span>
        <div className="flex gap-1.5 items-center">
          <PhaseChip phase={state.phase} />
          {state.active_fault && (
            <span className="text-[10px] font-mono text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">
              {state.active_fault.replace(/_/g, ' ').toUpperCase()}
            </span>
          )}
          {isHealthy && (
            <span className="text-[10px] text-green-400 bg-green-900/30 px-1.5 py-0.5 rounded">NORMAL</span>
          )}
        </div>
      </div>
      <ReactECharts
        option={option}
        style={{ height: 'calc(100% - 28px)', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  )
}
