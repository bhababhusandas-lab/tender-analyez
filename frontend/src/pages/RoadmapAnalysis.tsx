import { useState, useRef, useEffect } from 'react'
import { UsageLimitModal } from '../components/billing/UsageLimitModal'
import { DiscussionPanel } from '../components/discussion/DiscussionPanel'
import { Upload, FileText, Play, RotateCcw, AlertCircle, Loader2, ChevronDown, ChevronUp, CheckCircle, Trash2 } from 'lucide-react'
import { FinalQuoteCard } from '../components/tender/FinalQuoteCard'
import { MarkdownReport } from '../components/tender/MarkdownReport'
import { TenderHistoryPanel } from '../components/history/TenderHistoryPanel'
import { notifyHistoryChanged } from '../api/tenders'
import { TENDER_UPLOAD_ACCEPT, TENDER_UPLOAD_HINT } from '../utils/uploadTypes'

const JOB_KEY = 'taa_roadmap_job_id'

/**
 * Rewrites this page's query string without going through react-router.
 * The router never sees it, so the remount-on-navigate wrapper in App.tsx does
 * not remount the page mid-run; history.state is kept so the router's own
 * bookkeeping (key/idx) survives for back/forward.
 */
function replaceQuery(update: Record<string, string | null>) {
  const params = new URLSearchParams(window.location.search)
  for (const [name, value] of Object.entries(update)) {
    if (value === null) params.delete(name)
    else params.set(name, value)
  }
  const query = params.toString()
  window.history.replaceState(window.history.state, '', `/app/analysis${query ? `?${query}` : ''}`)
}

type Status = 'waiting' | 'processing' | 'done' | 'error'

const PHASES = [
  { id: 'phase-1-hunt',     num: 1, name: 'Hunt',     subtitle: 'Find the right tender / sector fit',   team: ['Market Intelligence', 'Bid Manager', 'Govt Liaison'],                                       color: 'violet' },
  { id: 'phase-2-qualify',  num: 2, name: 'Qualify',  subtitle: 'Bid / No-Bid decision',                team: ['Technical Expert', 'Finance', 'Legal', 'MD'],                                               color: 'emerald' },
  { id: 'phase-3-build',    num: 3, name: 'Build',    subtitle: 'Create the quotation',                 team: ['Technical', 'Finance', 'Pricing', 'Tech Writer', 'Legal', 'Admin/HR', 'Doc Controller'],     color: 'amber' },
  { id: 'phase-4-review',   num: 4, name: 'Review',   subtitle: 'Zero-defect audit',                    team: ['QA Reviewer', 'MD', 'Doc Controller'],                                                       color: 'orange' },
  { id: 'phase-5-submit',   num: 5, name: 'Submit',   subtitle: 'Portal submission plan',               team: ['IT Support', 'Doc Controller', 'Finance', 'Bid Manager'],                                    color: 'blue' },
  { id: 'phase-6-win',      num: 6, name: 'Win',      subtitle: 'Evaluation & negotiation',             team: ['Bid Manager', 'Pricing', 'Legal', 'Technical', 'Govt Liaison', 'MD'],                        color: 'rose' },
  { id: 'phase-7-execute',  num: 7, name: 'Execute',  subtitle: 'Contract delivery plan',               team: ['Admin/HR', 'Finance', 'Legal', 'Bid Manager', 'Technical', 'Govt Liaison'],                  color: 'lime' },
]

function PhaseCard({ phase, status, content, onRetry }: { phase: typeof PHASES[number]; status: Status; content?: string; onRetry?: () => void }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className={`overflow-hidden rounded-lg border bg-white transition-all duration-300 ${
      status === 'waiting' ? 'border-gray-200 opacity-55' :
      status === 'processing' ? 'border-slate-400 shadow-[0_4px_18px_-12px_rgba(15,23,42,.45)]' :
      status === 'error' ? 'border-red-300' :
      'border-gray-200 shadow-[0_3px_14px_-12px_rgba(15,23,42,.35)]'
    }`}>
      <div className={`flex items-center gap-3 px-4 py-3.5 ${status === 'done' ? 'cursor-pointer hover:bg-gray-50/70' : ''}`}
        onClick={() => status === 'done' && setExpanded(e => !e)}>
        <span className={`text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${
          status === 'waiting' ? 'bg-gray-200 text-gray-500' :
          status === 'processing' ? 'bg-slate-900 text-white' :
          status === 'error' ? 'bg-red-500 text-white' :
          'bg-slate-800 text-white'
        }`}>{phase.num}</span>

        <div className="flex-1 min-w-0">
          <div className={`font-medium text-sm ${status === 'waiting' ? 'text-gray-400' : 'text-gray-900'}`}>
            Phase {phase.num} — {phase.name}
          </div>
          <div className="text-xs text-gray-500 mt-0.5 truncate">{phase.subtitle}</div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {phase.team.map(t => (
              <span key={t} className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${status === 'waiting' ? 'border-gray-100 bg-gray-50 text-gray-400' : 'border-gray-200 bg-gray-50 text-gray-600'}`}>{t}</span>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {status === 'waiting' && <span className="text-xs text-gray-400">Waiting…</span>}
          {status === 'processing' && (
            <div className="flex items-center gap-1.5 text-slate-700">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span className="text-xs font-medium">Analyzing…</span>
            </div>
          )}
          {status === 'done' && (
            <div className="flex items-center gap-1.5 text-emerald-700">
              <CheckCircle className="w-4 h-4" />
              <span className="text-xs font-medium">Complete</span>
              {expanded ? <ChevronUp className="w-3.5 h-3.5 text-gray-400" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-400" />}
            </div>
          )}
          {status === 'error' && (
            <div className="flex items-center gap-1.5 text-red-600">
              <AlertCircle className="w-4 h-4" />
              <span className="text-xs font-medium">Error</span>
              {onRetry && <button type="button" onClick={(event) => { event.stopPropagation(); onRetry() }}
                className="ml-2 rounded-md border border-red-200 bg-white px-2 py-1 text-[11px] font-semibold text-red-700 hover:bg-red-50">Retry</button>}
            </div>
          )}
        </div>
      </div>

      {status === 'done' && expanded && content && (
        <div className="border-t border-gray-200 bg-gray-50/40 px-5 py-5 sm:px-6">
          <MarkdownReport content={content} />
        </div>
      )}
    </div>
  )
}

export function RoadmapAnalysis() {
  const [tenderText, setTenderText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [running, setRunning] = useState(false)
  const [started, setStarted] = useState(false)
  const [phases, setPhases] = useState<Record<string, { status: Status; content?: string }>>(
    Object.fromEntries(PHASES.map(p => [p.id, { status: 'waiting' as Status }]))
  )
  const [finalLoading, setFinalLoading] = useState(false)
  const [finalContent, setFinalContent] = useState<string | undefined>()
  const [error, setError] = useState('')
  const [usageLimit, setUsageLimit] = useState<import('../api/usage').UsageLimitInfo | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [tenderId, setTenderId] = useState<number | null>(() => {
    const value = Number(new URLSearchParams(window.location.search).get('tender'))
    return Number.isInteger(value) && value > 0 ? value : null
  })
  // Aborted on unmount (e.g. the sidebar opens another tender). Jobs run detached
  // on the server, so this only stops this page's stream watcher; every stream
  // fetch passes this signal.
  const pageAbortRef = useRef(new AbortController())

  const fileRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  const reset = () => {
    setTenderText(''); setFiles([]); setStarted(false); setRunning(false)
    setPhases(Object.fromEntries(PHASES.map(p => [p.id, { status: 'waiting' as Status }])))
    setFinalLoading(false); setFinalContent(undefined); setError('')
    setJobId(null); localStorage.removeItem(JOB_KEY)
    // Start clean: the next run files its own tender, so drop the old one from the panel and URL.
    setTenderId(null); replaceQuery({ tender: null, job: null })
  }

  const setPhaseState = (id: string, update: Partial<{ status: Status; content?: string }>) =>
    setPhases(prev => ({ ...prev, [id]: { ...prev[id], ...update } }))

  /** Reads one SSE stream. Once `signal` aborts it stops touching state, localStorage and the URL. */
  const consumeRoadmapStream = async (response: Response, signal: AbortSignal) => {
    if (!response.ok) throw new Error('Server error')
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (signal.aborted) return
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n'); buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (signal.aborted) return
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw === '[DONE]') { setRunning(false); continue }
          try {
            const evt = JSON.parse(raw)
            if (evt.type === 'tender') {
              // A new analysis was filed under a tender (sent before job_created).
              setTenderId(evt.tender_id)
              replaceQuery({ tender: String(evt.tender_id), job: null, new: null })
              notifyHistoryChanged()
            }
            if (evt.type === 'job_created') {
              setJobId(evt.job_id); localStorage.setItem(JOB_KEY, evt.job_id)
              replaceQuery({ job: evt.job_id, new: null })
            }
            if (evt.type === 'phase_start') setPhaseState(evt.phase_id, { status: 'processing' })
            if (evt.type === 'phase_done') setPhaseState(evt.phase_id, { status: 'done', content: evt.content })
            if (evt.type === 'phase_error') setPhaseState(evt.phase_id, { status: 'error', content: evt.message })
            if (evt.type === 'final_start') setFinalLoading(true)
            if (evt.type === 'final_done') { setFinalLoading(false); setFinalContent(evt.content); notifyHistoryChanged() }
            if (evt.type === 'job_paused') { setRunning(false); notifyHistoryChanged() }
            if (evt.type === 'job_cancelled') { setRunning(false); setFinalLoading(false); notifyHistoryChanged() }
            if (evt.type === 'error') { setError(evt.message); setRunning(false); notifyHistoryChanged() }
          } catch { /* incomplete event */ }
        }
      }
    } finally {
      // The tender version commits after final_done; refresh the sidebar/panel once the stream ends.
      if (!signal.aborted) notifyHistoryChanged()
    }
  }

  // Mount effect: restore the job, and abort every stream watcher on unmount.
  // No run-once ref: under StrictMode the first pass is aborted by its own
  // cleanup and the second pass redoes the (idempotent) restore.
  useEffect(() => {
    const controller = new AbortController()
    pageAbortRef.current = controller
    const { signal } = controller
    const cleanup = () => controller.abort()
    const query = new URLSearchParams(window.location.search)
    if (query.get('new') === '1') {
      localStorage.removeItem(JOB_KEY)
      setTenderId(null)
      window.history.replaceState(window.history.state, '', '/app/analysis')
      return cleanup
    }
    // ?job= (from the history sidebar/panel) picks the run to show.
    const jobParam = query.get('job')
    if (jobParam) localStorage.setItem(JOB_KEY, jobParam)
    // ?tender= without a job: the tender has no run to show yet. Don't paint
    // whatever unrelated job is left in localStorage under its panel.
    else if (query.get('tender')) return cleanup
    const savedJobId = localStorage.getItem(JOB_KEY)
    if (!savedJobId) return cleanup
    const restore = async () => {
      const base = (window as any).API_URL ?? import.meta.env.VITE_API_URL ?? ''
      const token = localStorage.getItem('taa_token') || ''
      const headers = token ? { Authorization: `Bearer ${token}` } : undefined
      const response = await fetch(`${base}/api/v1/analysis-jobs/${savedJobId}`, { headers, signal })
      if (signal.aborted) return
      if (!response.ok) {
        localStorage.removeItem(JOB_KEY)
        if (jobParam && response.status === 404) setError('This analysis is no longer available.')
        return
      }
      const job = await response.json()
      if (signal.aborted) return
      setJobId(savedJobId); setStarted(true)
      for (const step of job.steps ?? []) {
        if (step.id === 'md-final') continue
        const status: Status = step.status === 'done' ? 'done' : step.status === 'error' ? 'error' : step.status === 'running' ? 'processing' : 'waiting'
        setPhaseState(step.id, { status, content: step.content || step.error })
      }
      if (job.final_content) setFinalContent(job.final_content)
      if (job.status === 'running' || job.status === 'pending') {
        setRunning(true)
        const resumed = await fetch(`${base}/api/v1/tender/analyze-roadmap/${savedJobId}/resume`, { method: 'POST', headers, signal })
        await consumeRoadmapStream(resumed, signal)
      }
    }
    restore().catch(() => { if (!signal.aborted) setError('Could not restore the previous roadmap analysis.') })
    return cleanup
  }, [])

  const analyze = async () => {
    if (!tenderText.trim() && files.length === 0) { setError('Please paste tender details or upload one or more documents.'); return }
    setError(''); setStarted(true); setRunning(true)
    setPhases(Object.fromEntries(PHASES.map(p => [p.id, { status: 'waiting' as Status }])))
    setFinalContent(undefined)
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 200)

    const fd = new FormData()
    files.forEach(file => fd.append('files', file))
    fd.append('tender_text', tenderText)

    const signal = pageAbortRef.current.signal
    try {
      const base = (window as any).API_URL ?? import.meta.env.VITE_API_URL ?? ''
      const token = localStorage.getItem('taa_token') || ''
      const response = await fetch(`${base}/api/v1/tender/analyze-roadmap`, {
        method: 'POST',
        body: fd,
        signal,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (response.status === 402) {
        const body = await response.json().catch(() => null)
        const info = body?.detail ?? body
        if (info?.code === 'USAGE_LIMIT_EXCEEDED') {
          setStarted(false); setRunning(false)
          setUsageLimit(info)
          return
        }
      }
      await consumeRoadmapStream(response, signal)
    } catch {
      if (!signal.aborted) setError('Analysis failed. Make sure the backend is running.')
    } finally { setRunning(false) }
  }

  const retryPhase = async (phaseId: string) => {
    if (!jobId) return
    setPhaseState(phaseId, { status: 'processing', content: undefined }); setRunning(true); setError('')
    const signal = pageAbortRef.current.signal
    try {
      const base = (window as any).API_URL ?? import.meta.env.VITE_API_URL ?? ''
      const token = localStorage.getItem('taa_token') || ''
      const response = await fetch(`${base}/api/v1/tender/analyze-roadmap/${jobId}/retry/${phaseId}`, {
        method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : undefined, signal,
      })
      await consumeRoadmapStream(response, signal)
    } catch {
      if (signal.aborted) return
      setPhaseState(phaseId, { status: 'error', content: 'Retry could not be started.' })
    } finally { setRunning(false) }
  }

  // An error before any step ran (e.g. an unreadable upload) is a failed run, not a finished one.
  const failed = !running && !!error && !finalContent
  const showSteps = !failed || Object.values(phases).some(step => step.status !== 'waiting')

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      {usageLimit && <UsageLimitModal info={usageLimit} onClose={() => setUsageLimit(null)} />}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-gray-900">Tender Analysis · 7-Phase Roadmap</h1>
        <p className="text-sm text-gray-500 mt-0.5">Your team works through Hunt → Qualify → Build → Review → Submit → Win → Execute. The MD ties it all into a final quote.</p>
      </div>

      {/* Tender history: versions, documents, re-analyse (shown above the form or the results) */}
      {tenderId && <TenderHistoryPanel tenderId={tenderId} activeJobId={jobId} defaultKind="roadmap" />}

      {!started && (
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Paste Tender Details</label>
            <textarea value={tenderText} onChange={e => setTenderText(e.target.value)}
              placeholder={`Paste full tender text — title, scope, eligibility, technical specs, EMD, deadline, T&C…`}
              rows={12} className="w-full text-sm border border-gray-200 rounded-xl px-4 py-3.5 outline-none focus:border-gray-400 resize-none leading-relaxed" />
          </div>
          <div className="flex items-center gap-3"><div className="flex-1 h-px bg-gray-200" /><span className="text-xs text-gray-400 font-medium">OR</span><div className="flex-1 h-px bg-gray-200" /></div>
          <div onClick={() => fileRef.current?.click()}
            onDrop={e => { e.preventDefault(); const dropped = Array.from(e.dataTransfer.files); if (dropped.length) setFiles(current => [...current, ...dropped].slice(0, 10)) }}
            onDragOver={e => e.preventDefault()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${files.length ? 'border-gray-400 bg-gray-50' : 'border-gray-200 hover:border-gray-400 hover:bg-gray-50'}`}>
            {files.length ? (
              <div className="space-y-2 text-left">
                <p className="text-xs font-semibold text-gray-600 text-center mb-3">{files.length} document{files.length === 1 ? '' : 's'} selected</p>
                {files.map((file, index) => (
                  <div key={`${file.name}-${file.size}-${index}`} className="flex items-center gap-3 bg-white border border-gray-200 rounded-lg px-3 py-2">
                    <FileText className="w-5 h-5 text-blue-500 flex-shrink-0" />
                    <div className="min-w-0 flex-1"><p className="font-medium text-gray-900 text-sm truncate">{file.name}</p><p className="text-xs text-gray-400">{(file.size / 1024).toFixed(0)} KB</p></div>
                    <button type="button" aria-label={`Remove ${file.name}`} onClick={e => { e.stopPropagation(); setFiles(current => current.filter((_, i) => i !== index)) }} className="text-gray-400 hover:text-red-500 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                <p className="text-xs text-blue-600 text-center pt-1">Click or drop more files · maximum 10</p>
              </div>
            ) : (<><Upload className="w-7 h-7 text-gray-300 mx-auto mb-2" /><p className="text-sm text-gray-500">Upload tender documents</p><p className="text-xs text-gray-400 mt-1">{TENDER_UPLOAD_HINT}</p></>)}
            <input ref={fileRef} type="file" multiple accept={TENDER_UPLOAD_ACCEPT} className="hidden" onChange={e => { const selected = Array.from(e.target.files ?? []); if (selected.length) setFiles(current => [...current, ...selected].slice(0, 10)); e.target.value = '' }} />
          </div>
          {error && <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 px-4 py-3 rounded-xl"><AlertCircle className="w-4 h-4 flex-shrink-0" />{error}</div>}
          <button onClick={analyze} className="w-full py-3.5 bg-gray-900 text-white font-semibold rounded-xl hover:bg-gray-700 flex items-center justify-center gap-2.5 text-sm">
            <Play className="w-4 h-4" /> Run 7-Phase Roadmap Analysis
          </button>
          <div className="flex items-center justify-center gap-2 flex-wrap pt-1">
            {PHASES.map((p, i) => (
              <span key={p.id} className="flex items-center gap-1.5 text-xs text-gray-400">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-slate-800 text-[10px] font-bold text-white">{p.num}</span>
                {p.name}{i < PHASES.length - 1 && <span className="text-gray-200">→</span>}
              </span>
            ))}
            <span className="text-gray-200">→</span><span className="text-xs font-semibold text-gray-700">Final Quote</span>
          </div>
        </div>
      )}

      {started && (
        <div ref={resultsRef} className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-gray-900">{running ? 'Roadmap analysis in progress…' : failed ? 'Analysis could not run' : 'Analysis Complete'}</h2>
              <p className="text-xs text-gray-400 mt-0.5">{files.length ? `${files.length} document${files.length === 1 ? '' : 's'}: ${files.map(file => file.name).join(', ')}` : `${tenderText.slice(0, 60)}…`}</p>
            </div>
            {!running && (
              <button onClick={reset} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 border border-gray-200 rounded-lg px-3 py-1.5 hover:border-gray-400">
                <RotateCcw className="w-3 h-3" /> New Tender
              </button>
            )}
          </div>

          {error && (
            <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-300 bg-red-50 px-5 py-4 text-sm text-red-900">
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600" />
              <div>
                <p className="font-semibold">{failed ? 'The analysis could not run' : 'Something went wrong'}</p>
                <p className="mt-1 whitespace-pre-line text-red-800">{error}</p>
                {failed && <p className="mt-2 text-xs text-red-700">Fix the file or paste the tender text, then click New Tender to try again.</p>}
              </div>
            </div>
          )}

          {showSteps && (
            <div className="space-y-3">
              {PHASES.map(p => (
                <PhaseCard key={p.id} phase={p} status={phases[p.id]?.status ?? 'waiting'} content={phases[p.id]?.content}
                  onRetry={() => retryPhase(p.id)} />
              ))}
            </div>
          )}

          {(finalLoading || finalContent) && <FinalQuoteCard loading={finalLoading} content={finalContent} />}

          {finalContent && (
            <DiscussionPanel
              kind="roadmap"
              tenderText={tenderText || files.map(file => file.name).join(', ')}
              analysisResults={Object.fromEntries(
                Object.entries(phases)
                  .filter(([, v]) => v.status === 'done' && v.content)
                  .map(([k, v]) => [k, v.content as string])
              )}
              finalBriefing={finalContent}
              tenderId={tenderId}
              jobId={jobId}
            />
          )}
        </div>
      )}
    </div>
  )
}
