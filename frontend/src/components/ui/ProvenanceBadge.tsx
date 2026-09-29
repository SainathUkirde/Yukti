/* src/components/ui/ProvenanceBadge.tsx
 * Tiny badge showing the provenance tag of a value.
 */
import { PROVENANCE_BG, PROVENANCE_LABELS } from '@/types/provenance'
import type { ProvenanceTag } from '@/types/provenance'
import clsx from 'clsx'

interface Props {
  tag: ProvenanceTag | string
  className?: string
}

export function ProvenanceBadge({ tag, className }: Props) {
  const bg = PROVENANCE_BG[tag as ProvenanceTag] ?? 'bg-gray-900/40 text-gray-400'
  const label = PROVENANCE_LABELS[tag as ProvenanceTag] ?? tag
  return (
    <span className={clsx('badge-prov', bg, className)}>
      {label}
    </span>
  )
}
