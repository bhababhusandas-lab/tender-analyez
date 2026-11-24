import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Loader2, Pencil, Plus, Search } from 'lucide-react'
import { fetchTenders, HISTORY_CHANGED, notifyHistoryChanged, renameTender, runUrl, TenderListItem } from '../../api/tenders'
import { groupByDay } from './historyGroups'

/** Claude-style conversation list of the user's tenders, inside the dashboard rail. */
export function SidebarHistory({ onNavigate }: { onNavigate?: () => void }) {
  const [items, setItems] = useState<TenderListItem[]>([])
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  // useLocation re-renders on router navigations; the value is read from
  // window.location because the analysis pages add ?tender= with
  // history.replaceState, which the router never sees. HISTORY_CHANGED
  // (fired when a run files its tender) re-renders via `tick`.
  useLocation()
  const [, setTick] = useState(0)
  const activeTender = new URLSearchParams(window.location.search).get('tender')
  const requestSeq = useRef(0)

  // Debounce what the user types before it drives a fetch.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(text), 250)
    return () => window.clearTimeout(timer)
  }, [text])

  const load = useCallback(async () => {
    const seq = ++requestSeq.current
    try {
      const results = await fetchTenders(query, 20)
      if (seq === requestSeq.current) setItems(results)
    } catch { /* keep the last list */ }
  }, [query])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const refresh = () => { setTick(t => t + 1); load() }
    window.addEventListener(HISTORY_CHANGED, refresh)
    // Running analyses finish in the background; poll gently so the dot appears,
    // but not while the tab is hidden — refresh once when it becomes visible again.
    const timer = window.setInterval(() => { if (!document.hidden) refresh() }, 20_000)
    const onVisibility = () => { if (!document.hidden) refresh() }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener(HISTORY_CHANGED, refresh)
      document.removeEventListener('visibilitychange', onVisibility)
      window.clearInterval(timer)
    }
  }, [load])

  const saveRename = async (item: TenderListItem) => {
    const name = draft.trim()
    setEditingId(null)
    if (!name || name === item.name) return
    try { await renameTender(item.id, name); notifyHistoryChanged() } catch { /* keep the old name */ }
  }

  return (
    <div className="pt-1">
      <div className="flex items-center justify-between px-4 pb-1.5">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">History</p>
        <button onClick={() => setSearching(s => !s)} aria-label="Search tenders" aria-expanded={searching}
          className="text-steel-400 hover:text-white transition-colors">
          <Search className="w-3.5 h-3.5" />
        </button>
      </div>
      {searching && (
        <div className="px-3 pb-2">
          <input autoFocus value={text} onChange={e => setText(e.target.value)} placeholder="Search tenders"
            aria-label="Search tenders"
            className="w-full rounded-md bg-navy-800 border border-navy-700 px-2.5 py-1.5 text-xs text-white placeholder-steel-400 outline-none focus:border-saffron-500" />
        </div>
      )}
      <Link to="/app/bid?new=1" onClick={onNavigate}
        className="mx-3 mb-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-steel-300 hover:bg-navy-800/60 hover:text-white transition-colors">
        <Plus className="w-3.5 h-3.5" /> New analysis
      </Link>
      {items.length === 0 && (
        <p className="px-4 py-2 text-xs text-steel-400">{query ? 'No matching tenders.' : 'Tenders you analyse will appear here.'}</p>
      )}
      {groupByDay(items).map(group => (
        <div key={group.label} className="mb-2">
          <p className="px-4 pt-2 pb-1 text-[11px] text-steel-400">{group.label}</p>
          {group.items.map(item => {
            const active = activeTender === String(item.id)
            return (
              <div key={item.id} className={`group flex items-center pr-1 transition-colors
                  ${active ? 'bg-navy-800 text-white' : 'text-steel-300 hover:bg-navy-800/60 hover:text-white'}`}>
                {editingId === item.id ? (
                  <input autoFocus value={draft} onChange={e => setDraft(e.target.value)} maxLength={300}
                    aria-label="Tender name"
                    onKeyDown={e => { if (e.key === 'Enter') saveRename(item); if (e.key === 'Escape') setEditingId(null) }}
                    onBlur={() => saveRename(item)}
                    className="mx-3 my-1 flex-1 min-w-0 rounded bg-navy-900 border border-saffron-500 px-2 py-1 text-[13px] text-white outline-none" />
                ) : (
                  <>
                    <Link to={runUrl(item.id, item.latest_kind, item.latest_job_id)} onClick={onNavigate} title={item.name}
                      className="flex min-w-0 flex-1 items-center gap-2 pl-4 pr-2 py-1.5 text-[13px]">
                      <span className="truncate flex-1">{item.name}</span>
                      {item.running && <><Loader2 className="w-3 h-3 flex-none animate-spin text-steel-400" aria-hidden="true" /><span className="sr-only">Analysis running</span></>}
                      {!item.running && item.unread && <><span className="w-1.5 h-1.5 flex-none rounded-full bg-saffron-500" aria-hidden="true" /><span className="sr-only">New result</span></>}
                    </Link>
                    <button onClick={() => { setDraft(item.name); setEditingId(item.id) }} aria-label={`Rename ${item.name}`} title="Rename"
                      className="flex-none p-1.5 text-steel-400 opacity-0 transition-opacity hover:text-white focus:opacity-100 group-hover:opacity-100">
                      <Pencil className="w-3 h-3" />
                    </button>
                  </>
                )}
              </div>
            )
          })}
        </div>
      ))}
      <Link to="/app/history" onClick={onNavigate}
        className="block px-4 py-1.5 text-xs text-steel-400 hover:text-white transition-colors">View all</Link>
    </div>
  )
}
