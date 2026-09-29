/* src/components/ui/NavBar.tsx
 * Top navigation bar — links to all pages.
 * Added above Dashboard; existing Dashboard layout is untouched.
 */
import { NavLink } from 'react-router-dom'
import clsx from 'clsx'
import { useStore } from '@/store/useStore'
import { auditApi } from '@/api/features'
import { useEffect, useState } from 'react'

const PAGES = [
  { path: '/',          label: 'Dashboard' },
  { path: '/audit',     label: 'Audit'     },
  { path: '/rod-life',  label: 'Rod Life'  },
  { path: '/field',     label: 'Field'     },
  { path: '/calibrate', label: 'Calibrate' },
  { path: '/carbon',    label: 'Carbon'    },
  { path: '/handover',  label: 'Handover'  },
]

export function NavBar() {
  const { connected } = useStore()
  const [safeMode, setSafeMode] = useState(false)
  const [role, setRole] = useState('Operator')

  useEffect(() => {
    auditApi.status().then(s => {
      setSafeMode(s.safe_mode_active)
      setRole(s.current_role)
    }).catch(() => {})
  }, [])

  const toggleSafe = async () => {
    const res = await auditApi.setSafeMode(!safeMode)
    setSafeMode(res.safe_mode_active)
  }

  return (
    <nav className="flex items-center bg-surface border-b border-border px-3 h-8 gap-1 flex-shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-1.5 mr-2 flex-shrink-0">
        <img src="/yukti-logo.png" alt="YUKTI Logo" className="h-5 w-5 object-contain rounded" />
        <span className="text-xs font-bold text-accent tracking-wide">YUKTI</span>
      </div>

      {/* Page links */}
      <div className="flex gap-0.5 flex-1">
        {PAGES.map(p => (
          <NavLink
            key={p.path}
            to={p.path}
            end={p.path === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors',
                isActive
                  ? 'bg-accent/20 text-accent font-semibold'
                  : 'text-muted hover:text-text hover:bg-white/5'
              )
            }
          >
            {p.label}
          </NavLink>
        ))}
      </div>

      {/* Safe-mode pill */}
      <button
        onClick={toggleSafe}
        title="Toggle safe-mode (clamps step sizes)"
        className={clsx(
          'text-[10px] px-2 py-0.5 rounded border font-semibold transition-colors ml-2',
          safeMode
            ? 'border-amber-600 bg-amber-900/40 text-amber-300'
            : 'border-border text-muted hover:border-amber-600/50'
        )}
      >
        🛡 {safeMode ? 'SAFE ON' : 'SAFE OFF'}
      </button>

      {/* Role badge */}
      <span className="text-[10px] text-muted ml-1 flex-shrink-0 hidden md:block">
        {role}
      </span>

      {/* Connection dot */}
      <span className={clsx('w-2 h-2 rounded-full ml-2 flex-shrink-0',
        connected ? 'bg-green-400' : 'bg-red-400'
      )} />
    </nav>
  )
}
