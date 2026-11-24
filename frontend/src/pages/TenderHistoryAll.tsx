import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { fetchTenders, HISTORY_CHANGED, runUrl, TenderListItem } from '../api/tenders'

const day = (iso: string) => new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).toLocaleDateString('en-IN')

/** Full, searchable list of the user's tenders ("View all" in the sidebar history). */
export function TenderHistoryAll() {
  const [items, setItems] = useState<TenderListItem[]>([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = () => {
      fetchTenders(q, 200)
        .then(list => { if (!cancelled) { setItems(list); setError('') } })
        .catch(() => { if (!cancelled) setError('Could not load your tender history.') })
        .finally(() => { if (!cancelled) setLoading(false) })
    }
    // Debounce typing so each keystroke doesn't hit the API.
    const timer = window.setTimeout(load, q ? 250 : 0)
    window.addEventListener(HISTORY_CHANGED, load)
    return () => { cancelled = true; window.clearTimeout(timer); window.removeEventListener(HISTORY_CHANGED, load) }
  }, [q])

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      <h1 className="text-xl font-bold text-gray-900">Tender history</h1>
      <p className="text-sm text-gray-500 mt-0.5">Every tender you have analysed, with its latest result.</p>
      <input aria-label="Search tenders" value={q} onChange={e => setQ(e.target.value)} placeholder="Search by name or reference number"
        className="mt-6 w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm outline-none focus:border-gray-400" />
      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
      <div className="mt-4 overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-2.5 font-semibold">Tender</th>
              <th className="px-3 py-2.5 font-semibold">Latest decision</th>
              <th className="px-3 py-2.5 font-semibold">Deadline</th>
              <th className="px-3 py-2.5 font-semibold">Versions</th>
              <th className="px-3 py-2.5 font-semibold">Last activity</th>
            </tr>
          </thead>
          <tbody>
            {items.map(t => (
              <tr key={t.id} className="border-t border-gray-100 hover:bg-gray-50/70">
                <td className="px-4 py-2.5">
                  <Link to={runUrl(t.id, t.latest_kind, t.latest_job_id)} className="inline-flex items-center gap-2 font-medium text-gray-900 hover:underline">
                    {t.name}
                    {t.running && <><Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" aria-hidden="true" /><span className="sr-only">Analysis running</span></>}
                    {!t.running && t.unread && <><span className="w-1.5 h-1.5 rounded-full bg-amber-500" aria-hidden="true" /><span className="sr-only">New result</span></>}
                  </Link>
                  {t.reference_no && <p className="text-xs text-gray-400">{t.reference_no}</p>}
                </td>
                <td className="px-3 py-2.5 text-gray-700">{t.latest_decision || '—'}</td>
                <td className="px-3 py-2.5 text-gray-700">{t.latest_deadline || '—'}</td>
                <td className="px-3 py-2.5 text-gray-700">{t.version_count}</td>
                <td className="px-3 py-2.5 text-gray-500">{t.last_activity_at ? day(t.last_activity_at) : '—'}</td>
              </tr>
            ))}
            {!loading && items.length === 0 && !error && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">{q ? 'No matching tenders.' : 'No tenders yet.'}</td></tr>
            )}
            {loading && items.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400"><Loader2 className="inline w-4 h-4 animate-spin" aria-hidden="true" /><span className="sr-only">Loading</span></td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
