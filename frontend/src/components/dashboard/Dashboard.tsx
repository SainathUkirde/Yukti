/* src/components/dashboard/Dashboard.tsx
 * Main dashboard layout — SCADA-style dark theme.
 *
 * Layout (1920×1080 target):
 * ┌─────────────────────────────────────────────────────┐
 * │  StatusBar (top bar, 40px)                          │
 * ├─────────────────────────────────────────────────────┤
 * │  WellSelector (horizontal well cards, 70px)         │
 * ├──────────┬────────────────────────┬─────────────────┤
 * │ KPIPanel │  TrendChart            │ RightPanel      │
 * │ (200px)  │  (center, flex)        │ (tabs, 260px)   │
 * │          ├────────────────────────│                 │
 * │          │  DynoCardViewer        │                 │
 * │          │  (bottom half)         │                 │
 * └──────────┴────────────────────────┴─────────────────┘
 *
 * Right panel tabs: Optimizer | What-If | Faults | Assistant | Alerts
 *
 * Primary demo screen: All 11 KPIs visible without scrolling (KPIPanel).
 */
import { useEffect } from 'react'
import { useStore } from '@/store/useStore'
import { useWellStream } from '@/hooks/useWellStream'
import { wellsApi } from '@/api/wells'
import { optimizerApi } from '@/api/optimizer'
import { StatusBar } from './StatusBar'
import { WellSelector } from './WellSelector'
import { KPIPanel } from './KPIPanel'
import { TrendChart } from '@/components/charts/TrendChart'
import { DynoCardViewer } from '@/components/charts/DynoCardViewer'
import { OptimizerPanel } from '@/components/panels/OptimizerPanel'
import { WhatIfPanel } from '@/components/panels/WhatIfPanel'
import { FaultInjectionPanel } from '@/components/panels/FaultInjectionPanel'
import { AssistantPanel } from '@/components/panels/AssistantPanel'
import { AlertsPanel } from '@/components/panels/AlertsPanel'
import { reportApi } from '@/api/optimizer'
import clsx from 'clsx'

type RightTab = 'optimizer' | 'whatif' | 'faults' | 'assistant' | 'alerts'

const RIGHT_TABS: { id: RightTab; label: string; icon: string }[] = [
  { id: 'optimizer',  label: 'Optimize',  icon: '⚡' },
  { id: 'whatif',     label: 'What-If',   icon: '🔮' },
  { id: 'faults',     label: 'Faults',    icon: '⚠' },
  { id: 'assistant',  label: 'AI',        icon: '🤖' },
  { id: 'alerts',     label: 'Alerts',    icon: '🔔' },
]

function RightPanelTabs({ active, onChange }: {
  active: RightTab
  onChange: (t: RightTab) => void
}) {
  return (
    <div className="flex border-b border-border bg-surface">
      {RIGHT_TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={clsx(
            'flex-1 py-1.5 text-[10px] font-semibold transition-colors',
            active === t.id
              ? 'border-b-2 border-accent text-accent bg-accent/5'
              : 'text-muted hover:text-text'
          )}
        >
          <span className="block">{t.icon}</span>
          <span className="hidden lg:block">{t.label}</span>
        </button>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const {
    selectedWellId,
    setWellHistory,
    setRecommendations,
    activePanel,
    setActivePanel,
    recommendations,
  } = useStore()

  // Connect WebSocket for selected well
  useWellStream(selectedWellId)

  // Load history when well changes
  useEffect(() => {
    if (!selectedWellId) return
    wellsApi.history(selectedWellId, 100).then((res) => {
      setWellHistory(selectedWellId, res.ticks)
    }).catch(console.error)
  }, [selectedWellId, setWellHistory])

  // Periodically refresh recommendations
  useEffect(() => {
    const load = () => {
      optimizerApi.recommendations(selectedWellId ?? undefined).then((res) => {
        setRecommendations(res.recommendations)
      }).catch(console.error)
    }
    load()
    const interval = setInterval(load, 10_000)
    return () => clearInterval(interval)
  }, [selectedWellId, setRecommendations])

  const rightTab = activePanel as RightTab
  const setRightTab = (t: RightTab) => setActivePanel(t as typeof activePanel)

  const criticalCount = recommendations.filter((r) => r.priority === 'critical').length

  return (
    <div className="h-full flex flex-col bg-bg overflow-hidden">
      {/* Top bar */}
      <StatusBar />

      {/* Well selector strip */}
      <div className="px-3 py-1.5 bg-surface border-b border-border">
        <WellSelector />
      </div>

      {/* Main content area */}
      <div className="flex-1 flex min-h-0 gap-0">

        {/* LEFT: KPI Panel */}
        <div className="w-48 flex-shrink-0 p-2 border-r border-border">
          <KPIPanel />
        </div>

        {/* CENTER: Charts */}
        <div className="flex-1 flex flex-col min-w-0 gap-0">
          {/* Top: Trend chart */}
          <div className="flex-1 p-2 border-b border-border min-h-0">
            <TrendChart />
          </div>
          {/* Bottom: Dyno card */}
          <div className="flex-1 p-2 min-h-0">
            <DynoCardViewer />
          </div>
        </div>

        {/* RIGHT: Panel tabs */}
        <div className="w-64 flex-shrink-0 flex flex-col border-l border-border">
          <RightPanelTabs
            active={rightTab}
            onChange={setRightTab}
          />
          {/* Panel badge on alerts tab */}
          <div className="flex-1 p-2 overflow-hidden">
            {rightTab === 'optimizer'  && <OptimizerPanel />}
            {rightTab === 'whatif'     && <WhatIfPanel />}
            {rightTab === 'faults'     && <FaultInjectionPanel />}
            {rightTab === 'assistant'  && <AssistantPanel />}
            {rightTab === 'alerts'     && <AlertsPanel />}
          </div>
        </div>
      </div>

      {/* Footer: Provenance disclaimer + PDF download */}
      <div className="flex items-center justify-between px-4 py-1 border-t border-border bg-surface text-[9px] text-muted/60">
        <span>
          ALL DATA: SYNTHETIC_HISTORICAL / SIMULATED_LIVE — NOT validated on real Baghewala operations.
          Physics: Andrade (μ) · Marx-Langenheim · Vogel IPR · Gibbs wave eq
        </span>
        <div className="flex items-center gap-3">
          {criticalCount > 0 && (
            <span
              onClick={() => setRightTab('alerts')}
              className="cursor-pointer text-red-400 font-bold animate-pulse-slow"
            >
              ⚠ {criticalCount} CRITICAL
            </span>
          )}
          {selectedWellId && (
            <a
              href={reportApi.downloadUrl(selectedWellId)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1 rounded border border-accent/50 bg-accent/10 text-accent text-xs font-semibold hover:bg-accent/20 hover:border-accent transition-colors"
            >
              ↓ PDF Report
            </a>
          )}
          <span>v1.0 | YUKTI</span>
        </div>
      </div>
    </div>
  )
}
