import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Download, FileText, Loader2, Paperclip, Pencil, Trash2, X } from 'lucide-react'
import {
  deleteTender, downloadTenderDocument, downloadVersionPdf, fetchTender, HISTORY_CHANGED, markTenderViewed,
  notifyHistoryChanged, reanalyzeTender, renameTender, runUrl, RunKind, TenderDetail,
} from '../../api/tenders'
import { TENDER_UPLOAD_ACCEPT } from '../../utils/uploadTypes'

const FIELD_LABEL = { decision: 'Decision', quote: 'Quote', deadline: 'Deadline' } as const

/** Turns the re-analyse endpoint's 400 / 402 / 409 (and anything else) into one readable line. */
function reanalyseError(err: any): string {
  const status: number | undefined = err?.response?.status
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && typeof detail.message === 'string') return detail.message
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg
  if (status === 402) return 'You have reached your plan’s analysis limit.'
  if (status === 409) return 'An analysis of this tender is already running.'
  if (status === 400) return 'Add a note or a file to re-analyse.'
  return 'Re-analysis could not start. Please try again.'
}

/** localStorage keys where the analysis pages remember the job they show. */
const JOB_KEYS = ['taa_pipeline_job_id', 'taa_roadmap_job_id']

const when = (iso: string) =>
  new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })

/** Versions, what changed, documents and the "add update & re-analyse" box for one tender. */
export function TenderHistoryPanel({ tenderId, activeJobId, defaultKind }: {
  tenderId: number; activeJobId: string | null; defaultKind: RunKind
}) {
  const [tender, setTender] = useState<TenderDetail | null>(null)
  const [loadError, setLoadError] = useState('')
  const [note, setNote] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [kind, setKind] = useState<RunKind>(defaultKind)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileInput = useRef<HTMLInputElement | null>(null)
  const navigate = useNavigate()
  // The tender currently shown; a response for an earlier tenderId is dropped.
  const currentTender = useRef(tenderId)
  currentTender.current = tenderId

  const load = useCallback(async () => {
    try {
      const detail = await fetchTender(tenderId)
      if (currentTender.current !== tenderId) return
      setTender(detail); setLoadError('')
      // The user is looking at this tender, so a finished result is no longer "new".
      // Guarded by `unread`, so the notify → reload round trip stops after one pass.
      if (detail.unread && !detail.running) {
        markTenderViewed(tenderId).then(notifyHistoryChanged).catch(() => undefined)
      }
    } catch {
      if (currentTender.current === tenderId) setLoadError('Could not load this tender’s history.')
    }
  }, [tenderId])

  useEffect(() => {
    setTender(null); setLoadError('')
    load()
    // The analysis page fires this when a run starts or ends; keep versions current.
    window.addEventListener(HISTORY_CHANGED, load)
    return () => window.removeEventListener(HISTORY_CHANGED, load)
  }, [load])

  // The version's status commits a moment after the stream ends, so poll while
  // the server says a run is live; stop as soon as it isn't.
  const serverRunning = tender?.running ?? false
  useEffect(() => {
    if (!serverRunning) return
    const timer = window.setInterval(load, 4000)
    return () => window.clearInterval(timer)
  }, [serverRunning, load])

  if (!tender) {
    return loadError
      ? <section role="alert" className="mb-6 rounded-xl border border-gray-200 bg-white p-4 text-sm text-red-600">{loadError}</section>
      : null
  }
  // The server's flag ignores stale "running" rows left by a crashed process.
  const running = tender.running

  const submit = async () => {
    setBusy(true); setError('')
    try {
      const started = await reanalyzeTender(tenderId, kind, note, files)
      setNote(''); setFiles([]); notifyHistoryChanged()
      navigate(runUrl(started.tender_id, started.kind, started.job_id))
    } catch (err) {
      setError(reanalyseError(err))
    } finally { setBusy(false) }
  }

  const rename = async () => {
    const name = window.prompt('Rename tender', tender.name)?.trim()
    if (!name || name === tender.name) return
    try { await renameTender(tenderId, name); notifyHistoryChanged() }
    catch { setError('Could not rename this tender.') }
  }

  const remove = async () => {
    if (!window.confirm(`Delete "${tender.name}" and all its versions and files? This cannot be undone.`)) return
    try {
      await deleteTender(tenderId)
      // Don't let an analysis page try to restore a job that no longer exists.
      const jobIds = new Set(tender.versions.map(v => v.job_id).filter(Boolean))
      for (const key of JOB_KEYS) {
        try { if (jobIds.has(localStorage.getItem(key))) localStorage.removeItem(key) } catch { /* storage unavailable */ }
      }
      notifyHistoryChanged(); navigate('/app/history')
    }
    catch { setError('Could not delete this tender.') }
  }

  const download = (action: () => Promise<void>) => {
    action().catch(() => setError('Download failed. Please try again.'))
  }

  return (
    <section className="mb-6 rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Tender history</p>
          <h2 className="truncate text-base font-semibold text-gray-900" title={tender.name}>{tender.name}</h2>
        </div>
        <div className="flex gap-1">
          <button onClick={rename} aria-label="Rename tender" title="Rename" className="p-1.5 text-gray-400 hover:text-gray-900"><Pencil className="w-4 h-4" /></button>
          <button onClick={remove} aria-label="Delete tender" title="Delete" className="p-1.5 text-gray-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
        </div>
      </div>

      <ol className="mt-3 space-y-2">
        {tender.versions.map(v => {
          const open = v.job_id !== null && v.job_id === activeJobId
          const live = v.status === 'running' && tender.running
          const title = v.number ? `v${v.number}`
            : live ? 'Running'
            : v.status === 'running' ? 'Interrupted'
            : v.status === 'stopped' ? 'Stopped' : 'Failed'
          return (
            <li key={v.id} className={`rounded-lg border px-3 py-2 text-sm ${open ? 'border-gray-900' : 'border-gray-200'} ${v.number || live ? '' : 'opacity-60'}`}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-semibold text-gray-900">{title}</span>
                <span className="text-gray-600">{v.label}</span>
                {v.created_at && <span className="text-xs text-gray-400">{when(v.created_at)}</span>}
                {v.decision && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs font-semibold text-gray-700">{v.decision}</span>}
                <span className="ml-auto flex items-center gap-3 text-xs">
                  {live && <span className="inline-flex"><Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" aria-hidden="true" /><span className="sr-only">Analysis running</span></span>}
                  {open && <span className="text-gray-400">Showing</span>}
                  {!open && v.job_id && (
                    <Link to={runUrl(tenderId, v.kind, v.job_id)} aria-label={v.number ? `Open v${v.number}` : `Open or retry ${title.toLowerCase()} run`}
                      className="font-medium text-gray-700 hover:underline">{v.number ? 'Open' : live ? 'Open' : 'Open / Retry'}</Link>
                  )}
                  {v.number && <button onClick={() => download(() => downloadVersionPdf(tenderId, v.number!))} aria-label={`Summary PDF v${v.number}`} className="font-medium text-gray-700 hover:underline">Summary PDF</button>}
                </span>
              </div>
              {v.note && <p className="mt-1 text-xs text-gray-500">Note: {v.note}</p>}
              {v.changes.length > 0 && (
                <p className="mt-1 text-xs text-amber-700">
                  {v.changes.map(c => `${FIELD_LABEL[c.field] ?? c.field}: ${c.before || '—'} → ${c.after || '—'}`).join(' · ')}
                </p>
              )}
            </li>
          )
        })}
      </ol>

      {tender.documents.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Documents</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {tender.documents.map(d => (
              <li key={d.id}>
                <button onClick={() => download(() => downloadTenderDocument(tenderId, d))}
                  className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:border-gray-400">
                  <FileText className="w-3.5 h-3.5" /> {d.filename}
                  {d.version_number && <span className="text-gray-400">v{d.version_number}</span>}
                  <Download className="w-3 h-3 text-gray-400" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 rounded-lg border border-gray-300 p-3">
        <textarea aria-label="Update for re-analysis" value={note} onChange={e => setNote(e.target.value)} disabled={running || busy} rows={2}
          placeholder={running ? 'Analysis running…' : 'Add an update, e.g. "Corrigendum issued: deadline 07.10"'}
          className="w-full resize-none text-sm outline-none disabled:bg-transparent" />
        {files.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-2">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`} className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs">
                {f.name}
                <button onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`}><X className="w-3 h-3" /></button>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input ref={fileInput} type="file" multiple accept={TENDER_UPLOAD_ACCEPT} className="hidden"
            onChange={e => { const picked = Array.from(e.target.files ?? []); setFiles(current => [...current, ...picked]); e.target.value = '' }} />
          <button onClick={() => fileInput.current?.click()} disabled={running || busy}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-700 hover:text-gray-900 disabled:opacity-50">
            <Paperclip className="w-3.5 h-3.5" /> Add files
          </button>
          <select value={kind} onChange={e => setKind(e.target.value as RunKind)} disabled={running || busy}
            aria-label="Analysis type" className="ml-auto rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="pipeline">Bid Pipeline</option>
            <option value="roadmap">7-Phase Analysis</option>
          </select>
          <button onClick={submit} disabled={running || busy || (!note.trim() && files.length === 0)}
            className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-gray-700 disabled:opacity-40">
            {busy ? 'Starting…' : 'Re-analyse'}
          </button>
        </div>
        {error && <p role="alert" className="mt-2 text-xs text-red-600">{error}</p>}
      </div>
    </section>
  )
}
