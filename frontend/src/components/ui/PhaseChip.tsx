/* src/components/ui/PhaseChip.tsx
 * CSS cycle phase indicator chip.
 */
import clsx from 'clsx'

const PHASE_CLASSES: Record<string, string> = {
  injection:  'bg-blue-900/50 text-blue-300 border-blue-700/50',
  soak:       'bg-amber-900/50 text-amber-300 border-amber-700/50',
  production: 'bg-green-900/50 text-green-300 border-green-700/50',
  idle:       'bg-gray-900/50 text-gray-400 border-gray-700/50',
}

const PHASE_ICONS: Record<string, string> = {
  injection:  '💉',
  soak:       '🔥',
  production: '⛽',
  idle:       '⏸',
}

interface Props {
  phase: string
  className?: string
  showIcon?: boolean
}

export function PhaseChip({ phase, className, showIcon = true }: Props) {
  const cls = PHASE_CLASSES[phase] ?? PHASE_CLASSES.idle
  const icon = showIcon ? (PHASE_ICONS[phase] ?? '') : ''
  return (
    <span className={clsx(
      'inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border',
      cls, className
    )}>
      {icon && <span>{icon}</span>}
      {phase.toUpperCase()}
    </span>
  )
}
