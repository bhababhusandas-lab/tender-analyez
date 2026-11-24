import type { TenderListItem } from '../../api/tenders'

export interface HistoryGroup { label: string; items: TenderListItem[] }

const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`

/** Today / Yesterday / "Sep 24" (last 7 days) / Older — like the Claude chat list. */
export function groupByDay(items: TenderListItem[], now = new Date()): HistoryGroup[] {
  const today = dayKey(now)
  const yesterday = dayKey(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))
  const weekAgo = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6).getTime()
  const groups: HistoryGroup[] = []
  const push = (label: string, item: TenderListItem) => {
    const last = groups[groups.length - 1]
    if (last && last.label === label) last.items.push(item)
    else groups.push({ label, items: [item] })
  }
  for (const item of items) {
    const at = item.last_activity_at ? new Date(item.last_activity_at + (item.last_activity_at.endsWith('Z') ? '' : 'Z')) : null
    if (!at) { push('Older', item); continue }
    const key = dayKey(at)
    if (key === today) push('Today', item)
    else if (key === yesterday) push('Yesterday', item)
    else if (at.getTime() >= weekAgo) push(at.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }), item)
    else push('Older', item)
  }
  return groups
}
