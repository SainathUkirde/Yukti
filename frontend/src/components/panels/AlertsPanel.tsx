/* src/components/panels/AlertsPanel.tsx
 * Real-time alerts feed — shows active faults, critical recommendations.
 */
import { useStore } from '@/store/useStore'
import { motion, AnimatePresence } from 'framer-motion'

export function AlertsPanel() {
  const { alerts, clearAlerts, recommendations } = useStore()

  const criticalRecs = recommendations.filter((r) => r.priority === 'critical')

  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-muted uppercase tracking-wide">
          Alerts & Recommendations
        </span>
        {alerts.length > 0 && (
          <button onClick={clearAlerts} className="text-[10px] text-muted hover:text-text">
            Clear
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-1.5">
        {/* Critical recommendations */}
        <AnimatePresence>
          {criticalRecs.map((rec) => (
            <motion.div
              key={rec.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              className="px-2 py-1.5 rounded border border-red-700/50 bg-red-900/20"
            >
              <div className="flex items-start gap-1.5">
                <span className="text-red-400 text-xs">⚠</span>
                <div>
                  <p className="text-xs font-semibold text-red-300">{rec.title}</p>
                  <p className="text-[10px] text-muted mt-0.5">{rec.action}</p>
                  <p className="text-[10px] text-muted/70 mt-0.5 italic">{rec.well_id}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* High priority recommendations */}
        {recommendations
          .filter((r) => r.priority === 'high')
          .map((rec) => (
            <div
              key={rec.id}
              className="px-2 py-1.5 rounded border border-amber-700/40 bg-amber-900/15"
            >
              <p className="text-xs font-semibold text-amber-300">{rec.title}</p>
              <p className="text-[10px] text-muted mt-0.5">{rec.action}</p>
              <p className="text-[10px] text-muted/70 mt-0.5">{rec.well_id}</p>
            </div>
          ))}

        {/* WebSocket alert messages */}
        {alerts.slice(0, 5).map((a, i) => (
          <div key={i} className="px-2 py-1 rounded bg-surface border border-border text-[10px] text-muted">
            {a}
          </div>
        ))}

        {criticalRecs.length === 0 && alerts.length === 0 && (
          <p className="text-xs text-muted/60 italic text-center mt-4">No active alerts</p>
        )}
      </div>
    </div>
  )
}
