/* src/components/charts/TrendChart.tsx
 * ECharts line chart for production/reservoir trends.
 * Shows temperature, viscosity, oil rate, rod risk over time.
 */
import ReactECharts from 'echarts-for-react'
import { useStore } from '@/store/useStore'
import { useMemo } from 'react'

const CHART_THEME = {
  backgroundColor: 'transparent',
  textStyle: { color: '#8b949e', fontSize: 10 },
}

interface Series {
  key: keyof import('@/types/well').HistoryTick
  name: string
  color: string
  unit: string
  yAxisIndex?: number
}

const SERIES_CONFIG: Series[] = [
  { key: 'reservoir_temp_c',          name: 'T_res (°C)',    color: '#f97316', unit: '°C' },
  { key: 'oil_rate_m3d',              name: 'Oil Rate',       color: '#3fb950', unit: 'm³/d', yAxisIndex: 1 },
  { key: 'pump_efficiency_fraction',  name: 'Pump Eff',       color: '#388bfd', unit: '',     yAxisIndex: 1 },
  { key: 'rod_float_risk_score',      name: 'Rod Risk',       color: '#f85149', unit: '',     yAxisIndex: 1 },
]

export function TrendChart() {
  const { wellHistory, selectedWellId } = useStore()
  const ticks = selectedWellId ? (wellHistory[selectedWellId] ?? []) : []

  const option = useMemo(() => {
    const x = ticks.map((t) => t.tick.toString())
    return {
      ...CHART_THEME,
      grid: { top: 28, right: 60, bottom: 28, left: 50 },
      xAxis: {
        type: 'category',
        data: x,
        axisLabel: { color: '#8b949e', fontSize: 9, interval: Math.floor(x.length / 5) || 0 },
        axisLine: { lineStyle: { color: '#30363d' } },
      },
      yAxis: [
        {
          type: 'value',
          name: '°C',
          nameTextStyle: { color: '#8b949e', fontSize: 9 },
          axisLabel: { color: '#8b949e', fontSize: 9 },
          splitLine: { lineStyle: { color: '#30363d', type: 'dashed' } },
          axisLine: { lineStyle: { color: '#30363d' } },
        },
        {
          type: 'value',
          name: 'Other',
          nameTextStyle: { color: '#8b949e', fontSize: 9 },
          axisLabel: { color: '#8b949e', fontSize: 9 },
          splitLine: { show: false },
          axisLine: { lineStyle: { color: '#30363d' } },
          min: 0,
          max: 100,
        },
      ],
      series: SERIES_CONFIG.map((s) => ({
        name: s.name,
        type: 'line',
        data: ticks.map((t) => {
          const v = t[s.key] as number
          // Normalize some to 0-100 for secondary axis
          if (s.yAxisIndex === 1) {
            if (s.key === 'pump_efficiency_fraction') return +(v * 100).toFixed(1)
            return +v.toFixed(2)
          }
          return +v.toFixed(2)
        }),
        yAxisIndex: s.yAxisIndex ?? 0,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: s.color, width: 1.5 },
        itemStyle: { color: s.color },
      })),
      legend: {
        data: SERIES_CONFIG.map((s) => s.name),
        textStyle: { color: '#8b949e', fontSize: 9 },
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        top: 2,
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        textStyle: { color: '#e6edf3', fontSize: 10 },
        axisPointer: { lineStyle: { color: '#388bfd' } },
      },
    }
  }, [ticks])

  if (ticks.length < 2) {
    return (
      <div className="card h-full flex items-center justify-center text-muted text-xs">
        Waiting for data…
      </div>
    )
  }

  return (
    <div className="card h-full">
      <span className="text-xs text-muted uppercase tracking-wide">Production Trend</span>
      <ReactECharts
        option={option}
        style={{ height: 'calc(100% - 20px)', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  )
}
