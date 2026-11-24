import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, X } from 'lucide-react'
import {
  DeadlineNotification, fetchNotifications, markNotificationsRead, NotificationsResponse,
} from '../../api/notifications'
import { HISTORY_CHANGED, runUrl } from '../../api/tenders'

const POLL_MS = 5 * 60 * 1000
const POPUP_KEY = 'taa:deadline-popup-shown'

/** Fetches deadline notifications; refreshes every 5 minutes and when history changes. */
export function useDeadlineNotifications() {
  const [data, setData] = useState<NotificationsResponse>({ unread_count: 0, items: [] })
  const [loaded, setLoaded] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setData(await fetchNotifications())
      setLoaded(true)
    } catch { /* keep the last good state; the next poll retries */ }
  }, [])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, POLL_MS)
    window.addEventListener(HISTORY_CHANGED, refresh)
    return () => { window.clearInterval(timer); window.removeEventListener(HISTORY_CHANGED, refresh) }
  }, [refresh])

  const markRead = useCallback(async (tenderId?: number) => {
    // Optimistic, then reconcile with the server.
    setData(d => {
      const items = d.items.map(i => (tenderId === undefined || i.tender_id === tenderId) ? { ...i, unread: false } : i)
      return { items, unread_count: items.filter(i => i.unread).length }
    })
    try { await markNotificationsRead(tenderId) } catch { /* reconciled below */ }
    refresh()
  }, [refresh])

  return { ...data, loaded, markRead }
}

type Tone = 'red' | 'amber' | 'neutral'
const toneOf = (s: DeadlineNotification['stage']): Tone =>
  s === 'today' || s === '1' || s === 'overdue' ? 'red' : s === '3' ? 'amber' : 'neutral'

const TONE_DOT: Record<Tone, string> = {
  red: 'bg-red-500', amber: 'bg-amber-500', neutral: 'bg-steel-400',
}
const TONE_TEXT: Record<Tone, string> = {
  red: 'text-red-400', amber: 'text-amber-300', neutral: 'text-steel-400',
}

const stageLabel = (n: DeadlineNotification) =>
  n.stage === 'today' ? 'Due today'
    : n.stage === 'overdue' ? `Overdue by ${-n.days_left}d`
    : `${n.days_left}d left`

type State = ReturnType<typeof useDeadlineNotifications>

const DeadlineContext = createContext<State | null>(null)

/** One shared poller for the bell(s) and the login popup. */
export function DeadlineProvider({ children }: { children: ReactNode }) {
  const state = useDeadlineNotifications()
  return <DeadlineContext.Provider value={state}>{children}</DeadlineContext.Provider>
}

export function useDeadlines(): State {
  const state = useContext(DeadlineContext)
  if (!state) throw new Error('useDeadlines must be used inside DeadlineProvider')
  return state
}

export function DeadlineBell({ state, align = 'left', light = false }: { state: State; align?: 'left' | 'right'; light?: boolean }) {
  const { items, unread_count, markRead } = state
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement | null>(null)
  const button = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); button.current?.focus() } }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  const label = unread_count > 0
    ? `Deadline notifications, ${unread_count} unread`
    : 'Deadline notifications'

  return (
    <div ref={root} className="relative">
      <button
        ref={button}
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls="deadline-panel"
        className={`relative p-2 rounded-card transition-colors ${light
          ? 'border border-edge bg-panel text-fg-muted hover:text-fg hover:bg-sunk'
          : 'text-steel-400 hover:text-white hover:bg-navy-800'}`}
      >
        <Bell className="w-[18px] h-[18px]" />
        {unread_count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-600 text-white text-[10px] font-bold leading-4 text-center">
            {unread_count > 9 ? '9+' : unread_count}
          </span>
        )}
      </button>

      {open && (
        <div
          id="deadline-panel"
          role="dialog"
          aria-label="Upcoming tender deadlines"
          className={`on-dark absolute top-full mt-2 z-50 w-80 max-w-[calc(100vw-1.5rem)] rounded-card border border-navy-600 bg-navy-900 text-white shadow-xl ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          <div className="flex items-center justify-between px-3 py-2.5 border-b border-navy-700">
            <h2 className="text-[13px] font-semibold">Upcoming deadlines</h2>
            <button
              type="button"
              onClick={() => markRead()}
              disabled={unread_count === 0}
              className="text-xs font-semibold text-saffron-400 hover:text-saffron-300 disabled:text-steel-500 disabled:cursor-default"
            >
              Mark all as read
            </button>
          </div>
          {items.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-steel-400">No upcoming deadlines</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto scrollbar-thin divide-y divide-navy-700">
              {items.map(n => {
                const tone = toneOf(n.stage)
                return (
                  <li key={n.tender_id}>
                    <Link
                      to={runUrl(n.tender_id, n.latest_kind, n.latest_job_id)}
                      onClick={() => { setOpen(false); if (n.unread) markRead(n.tender_id) }}
                      className="flex items-start gap-2.5 px-3 py-2.5 hover:bg-navy-800 transition-colors"
                    >
                      <span aria-hidden className={`mt-1.5 w-2 h-2 flex-none rounded-full ${TONE_DOT[tone]} ${n.unread ? '' : 'opacity-40'}`} />
                      <span className="min-w-0 flex-1">
                        <span className={`block text-[13px] truncate ${n.unread ? 'font-semibold text-white' : 'text-steel-300'}`}>{n.name}</span>
                        <span className={`block font-mono text-[11px] ${TONE_TEXT[tone]}`}>
                          {stageLabel(n)}
                          <span className="text-steel-400"> · {n.deadline_text}</span>
                        </span>
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

/** Once per browser session, a small non-blocking toast when something is unread. */
export function DeadlinePopup({ state }: { state: State }) {
  const { items, unread_count, loaded } = state
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!loaded || unread_count === 0) return
    try {
      if (sessionStorage.getItem(POPUP_KEY)) return
      sessionStorage.setItem(POPUP_KEY, '1')
    } catch { /* storage blocked: still show once per mount */ }
    setVisible(true)
  }, [loaded, unread_count])

  useEffect(() => {
    if (!visible) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setVisible(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [visible])

  if (!visible) return null
  const shown = items.filter(i => i.unread).slice(0, 5)
  if (shown.length === 0) return null

  return (
    <div
      role="dialog"
      aria-label="Upcoming tender deadlines"
      className="on-dark fixed z-50 bottom-4 right-4 left-4 sm:left-auto sm:w-96 rounded-card border border-navy-600 bg-navy-900 text-white shadow-2xl"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
        <h2 className="text-sm font-semibold">Upcoming tender deadlines</h2>
        <button type="button" onClick={() => setVisible(false)} aria-label="Close" className="p-1 rounded-card text-steel-400 hover:text-white hover:bg-navy-800">
          <X className="w-4 h-4" />
        </button>
      </div>
      <ul className="divide-y divide-navy-700">
        {shown.map(n => (
          <li key={n.tender_id} className="flex items-center gap-3 px-4 py-2.5">
            <span aria-hidden className={`w-2 h-2 flex-none rounded-full ${TONE_DOT[toneOf(n.stage)]}`} />
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-medium truncate">{n.name}</span>
              <span className={`block font-mono text-[11px] ${TONE_TEXT[toneOf(n.stage)]}`}>{stageLabel(n)}</span>
            </span>
            <Link
              to={runUrl(n.tender_id, n.latest_kind, n.latest_job_id)}
              onClick={() => { setVisible(false); state.markRead(n.tender_id) }}
              className="text-xs font-semibold text-saffron-400 hover:text-saffron-300"
            >
              View
            </Link>
          </li>
        ))}
      </ul>
      <div className="px-4 py-2.5 border-t border-navy-700 flex justify-end">
        <button type="button" onClick={() => setVisible(false)} className="text-xs font-semibold text-steel-300 hover:text-white">
          Dismiss
        </button>
      </div>
    </div>
  )
}
