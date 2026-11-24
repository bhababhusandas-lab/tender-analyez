import { useState, useRef } from 'react'
import { Upload, FileText, Play, RotateCcw, AlertCircle, Save, Download, CheckCircle, Trash2, Loader2, Plus, Square } from 'lucide-react'
import { AgentStepCard, StepStatus } from '../components/tender/AgentStepCard'
import { FinalQuoteCard } from '../components/tender/FinalQuoteCard'
import { createBid, downloadBidPdf } from '../api/bids'
import { fetchPastBids, uploadPastBid, deletePastBid, PastBid } from '../api/pastBids'
import { UsageLimitInfo } from '../api/usage'
import { UsageLimitModal } from '../components/billing/UsageLimitModal'
import { DiscussionPanel } from '../components/discussion/DiscussionPanel'
import { fetchCompanies, CompanyProfile } from '../api/company'
import { useEffect } from 'react'
import { TenderHistoryPanel } from '../components/history/TenderHistoryPanel'
import { notifyHistoryChanged } from '../api/tenders'
import { TENDER_UPLOAD_ACCEPT, TENDER_UPLOAD_HINT } from '../utils/uploadTypes'

const JOB_KEY = 'taa_pipeline_job_id'

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
  window.history.replaceState(window.history.state, '', `/app/bid${query ? `?${query}` : ''}`)
}

const PIPELINE_AGENTS = [
  { id: 'tender-brief',        name: 'Tender Brief AI',                      icon: 'clipboard-list' },
  { id: 'bid-manager',         name: 'Bid Manager AI',                       icon: 'file-text' },
  { id: 'market-intelligence', name: 'Market Intelligence Analyst AI',       icon: 'trending-up' },
  { id: 'legal-compliance',    name: 'Legal / Compliance AI',                icon: 'scale' },
  { id: 'govt-relations',      name: 'Govt Relations & Liaison Officer AI',  icon: 'landmark' },
  { id: 'technical-expert',    name: 'Technical Expert AI',                  icon: 'shield' },
  { id: 'technical-writer',    name: 'Technical Writer / Proposal Designer AI', icon: 'pen-tool' },
  { id: 'finance-accounts',    name: 'Finance & Accounts AI',                icon: 'clipboard-list' },
  { id: 'bid-pricing',         name: 'Bid Pricing Analyst AI',               icon: 'bar-chart' },
  { id: 'doc-controller',      name: 'Document Controller AI',               icon: 'briefcase' },
  { id: 'admin-hr',            name: 'Admin / HR AI',                        icon: 'users' },
  { id: 'qa-reviewer',         name: 'Quality Assurance (QA) Reviewer AI',   icon: 'badge-check' },
]

type AgentState = { status: StepStatus; content?: string }
type QualityIssue = { code?: string; severity?: string; message: string }
const initAgents = (): Record<string, AgentState> =>
  Object.fromEntries(PIPELINE_AGENTS.map(a => [a.id, { status: 'waiting' }]))

function extractSnippet(results: Record<string, string>) {
  const bm = results['bid-manager'] || ''
  const fin = results['finance-accounts'] || ''
  const quoteMatch = fin.match(/RECOMMENDED L1 QUOTE[:\s*]+₹\s*[\d,]+/i) || fin.match(/₹\s*[\d,]+/)
  const confMatch = bm.match(/BID\/NO-BID SCORE[:\s]+(\d+)/i)
  return {
    recommended_quote: quoteMatch ? quoteMatch[0].replace(/RECOMMENDED L1 QUOTE[:\s*]+/i, '').trim() : '',
    bid_confidence: confMatch ? `${confMatch[1]}/100` : '',
  }
}

export function TenderAnalysis() {
  const [tenderText, setTenderText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [running, setRunning] = useState(false)
  const [started, setStarted] = useState(false)
  const [agents, setAgents] = useState<Record<string, AgentState>>(initAgents())
  const [finalLoading, setFinalLoading] = useState(false)
  const [finalContent, setFinalContent] = useState<string | undefined>()
  const [allResults, setAllResults] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  // Non-fatal caveats the MD must read before trusting the conclusions
  // (e.g. company profile too thin to judge eligibility).
  const [warning, setWarning] = useState('')
  const [usageLimit, setUsageLimit] = useState<UsageLimitInfo | null>(null)
  const [savedBidId, setSavedBidId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [companies, setCompanies] = useState<CompanyProfile[]>([])
  const [companyMode, setCompanyMode] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [tenderId, setTenderId] = useState<number | null>(() => {
    const value = Number(new URLSearchParams(window.location.search).get('tender'))
    return Number.isInteger(value) && value > 0 ? value : null
  })
  const [stopped, setStopped] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [qualityPassed, setQualityPassed] = useState<boolean | null>(null)
  const [qualityIssues, setQualityIssues] = useState<QualityIssue[]>([])
  // Aborted on unmount (e.g. the sidebar opens another tender). Jobs run detached
  // on the server, so this only stops this page's stream watcher; every stream
  // fetch uses this signal or one linked to it.
  const pageAbortRef = useRef(new AbortController())
  const streamAbortRef = useRef<AbortController | null>(null)
  const stopRequestedRef = useRef(false)

  // Past bids RAG
  const [pastBids, setPastBids] = useState<PastBid[]>([])
  const [showRAG, setShowRAG] = useState(false)
  const [uploadingRAG, setUploadingRAG] = useState(false)
  const ragFileRef = useRef<HTMLInputElement>(null)
  const [ragForm, setRagForm] = useState({ title: '', department: '', contract_value: '', year_won: '', outcome: 'won' })

  const fileRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchPastBids().then(setPastBids)
    fetchCompanies().then(items => {
      setCompanies(items)
      if (items.length > 1) setCompanyMode('all')
      else if (items[0]?.id) setCompanyMode(String(items[0].id))
    })
  }, [])

  const reset = () => {
    setTenderText(''); setFiles([]); setStarted(false); setRunning(false)
    setAgents(initAgents()); setFinalLoading(false); setFinalContent(undefined)
    setAllResults({}); setError(''); setWarning(''); setSavedBidId(null)
    setStopped(false); setStopping(false); stopRequestedRef.current = false
    setQualityPassed(null); setQualityIssues([])
    streamAbortRef.current?.abort(); streamAbortRef.current = null
    setJobId(null); localStorage.removeItem(JOB_KEY)
    // A clean navigation prevents the one-time restore effect from repainting
    // a completed job when the user explicitly asks to start another tender.
    window.location.assign('/app/bid?new=1')
  }

  const setAgentState = (id: string, update: Partial<AgentState>) =>
    setAgents(prev => ({ ...prev, [id]: { ...prev[id], ...update } }))

  /** Reads one SSE stream. Once `signal` aborts it stops touching state, localStorage and the URL. */
  const consumeAnalysisStream = async (response: Response, signal: AbortSignal) => {
    if (!response.ok) throw new Error('Server error')
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    const collectedResults: Record<string, string> = {}
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
              setJobId(evt.job_id)
              localStorage.setItem(JOB_KEY, evt.job_id)
              replaceQuery({ job: evt.job_id, new: null })
            }
            if (evt.type === 'warning') setWarning(evt.message)
            if (evt.type === 'agent_start') setAgentState(evt.agent_id, { status: 'processing' })
            if (evt.type === 'agent_done') { setAgentState(evt.agent_id, { status: 'done', content: evt.content }); collectedResults[evt.agent_id] = evt.content }
            if (evt.type === 'agent_error') setAgentState(evt.agent_id, { status: 'error', content: evt.message })
            if (evt.type === 'final_start') setFinalLoading(true)
            if (evt.type === 'quality_gate') {
              setQualityPassed(Boolean(evt.passed))
              setQualityIssues(Array.isArray(evt.issues) ? evt.issues : [])
            }
            if (evt.type === 'final_done') {
              setFinalLoading(false); setFinalContent(evt.content)
              if (evt.all_results) { Object.assign(collectedResults, evt.all_results); setAllResults(evt.all_results) }
              notifyHistoryChanged()
            }
            if (evt.type === 'job_paused') { setRunning(false); notifyHistoryChanged() }
            if (evt.type === 'job_cancelled') { setStopped(true); setRunning(false); setFinalLoading(false); notifyHistoryChanged() }
            if (evt.type === 'error') { setError(evt.message); setRunning(false); notifyHistoryChanged() }
          } catch { /* incomplete event */ }
        }
      }
      setAllResults(previous => ({ ...previous, ...collectedResults }))
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
      setTenderText(''); setFiles([]); setStarted(false); setRunning(false)
      setAgents(initAgents()); setFinalLoading(false); setFinalContent(undefined)
      setAllResults({}); setError(''); setWarning(''); setSavedBidId(null); setJobId(null)
      setTenderId(null)
      window.history.replaceState(window.history.state, '', '/app/bid')
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
      const base = window.API_URL ?? import.meta.env.VITE_API_URL ?? ''
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
      const restoredResults: Record<string, string> = {}
      for (const step of job.steps ?? []) {
        if (step.id === 'md-final') continue
        const status: StepStatus = step.status === 'done' ? 'done' : step.status === 'error' ? 'error' : step.status === 'cancelled' ? 'cancelled' : step.status === 'running' ? 'processing' : 'waiting'
        setAgentState(step.id, { status, content: step.content || step.error })
        if (step.content) restoredResults[step.id] = step.content
      }
      setAllResults(restoredResults)
      if (job.final_content) setFinalContent(job.final_content)
      if (job.status === 'review_required') {
        setQualityPassed(false)
        try { setQualityIssues(JSON.parse(job.error || '[]')) }
        catch { setQualityIssues([{ message: 'The report requires human review before it can be saved or exported.' }]) }
      } else if (job.status === 'completed') {
        setQualityPassed(true); setQualityIssues([])
      }
      if (job.status === 'cancelled') setStopped(true)
      if (job.status === 'running' || job.status === 'pending') {
        setRunning(true)
        const resumed = await fetch(`${base}/api/v1/tender/analyze/${savedJobId}/resume`, { method: 'POST', headers, signal })
        await consumeAnalysisStream(resumed, signal)
      }
    }
    restore().catch(() => { if (!signal.aborted) setError('Could not restore the previous analysis job.') })
    return cleanup
  }, [])

  const analyze = async () => {
    if (!tenderText.trim() && files.length === 0) { setError('Please paste tender details or upload one or more documents.'); return }
    setError(''); setWarning(''); setStopped(false); stopRequestedRef.current = false; setStarted(true); setRunning(true); setAgents(initAgents()); setFinalContent(undefined); setAllResults({}); setSavedBidId(null); setQualityPassed(null); setQualityIssues([])
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 200)

    const fd = new FormData()
    files.forEach(file => fd.append('files', file))
    fd.append('tender_text', tenderText)
    if (companyMode === 'all') fd.append('compare_all_companies', 'true')
    else if (companyMode) fd.append('company_profile_id', companyMode)

    let signal: AbortSignal | undefined
    try {
      const base = window.API_URL ?? import.meta.env.VITE_API_URL ?? ''
      const token = localStorage.getItem('taa_token') || ''
      // Aborted by Stop (streamAbortRef) or by unmount (linked to the page signal).
      const controller = new AbortController()
      streamAbortRef.current = controller
      const pageSignal = pageAbortRef.current.signal
      if (pageSignal.aborted) controller.abort()
      else pageSignal.addEventListener('abort', () => controller.abort(), { once: true })
      signal = controller.signal
      const response = await fetch(`${base}/api/v1/tender/analyze`, {
        method: 'POST',
        body: fd,
        signal: controller.signal,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (response.status === 402) {
        const body = await response.json().catch(() => null)
        const info = body?.detail ?? body
        if (info?.code === 'USAGE_LIMIT_EXCEEDED') {
          setStarted(false); setRunning(false)
          setUsageLimit(info as UsageLimitInfo)
          return
        }
      }
      await consumeAnalysisStream(response, controller.signal)
    } catch {
      if (!signal?.aborted && !stopRequestedRef.current) setError('Analysis failed. Make sure the backend is running.')
    } finally { setRunning(false); streamAbortRef.current = null }
  }

  const stopAnalysis = async () => {
    if (!jobId || stopping) return
    setStopping(true); setError(''); stopRequestedRef.current = true
    try {
      const base = window.API_URL ?? import.meta.env.VITE_API_URL ?? ''
      const token = localStorage.getItem('taa_token') || ''
      const response = await fetch(`${base}/api/v1/tender/analyze/${jobId}/cancel`, {
        method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (!response.ok) throw new Error('Stop request failed')
      streamAbortRef.current?.abort()
      setAgents(previous => Object.fromEntries(Object.entries(previous).map(([id, state]) => [
        id, state.status === 'waiting' || state.status === 'processing' ? { ...state, status: 'cancelled' as StepStatus } : state,
      ])))
      setFinalLoading(false); setRunning(false); setStopped(true)
      localStorage.removeItem(JOB_KEY)
      notifyHistoryChanged()
    } catch {
      stopRequestedRef.current = false
      setError('Could not stop the analysis. Please try again.')
    } finally { setStopping(false) }
  }

  const retryAgent = async (agentId: string) => {
    if (!jobId) return
    setAgentState(agentId, { status: 'processing', content: undefined })
    setRunning(true); setError('')
    const signal = pageAbortRef.current.signal
    try {
      const base = window.API_URL ?? import.meta.env.VITE_API_URL ?? ''
      const token = localStorage.getItem('taa_token') || ''
      const response = await fetch(`${base}/api/v1/tender/analyze/${jobId}/retry/${agentId}`, {
        method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : undefined, signal,
      })
      await consumeAnalysisStream(response, signal)
    } catch {
      if (signal.aborted) return
      setAgentState(agentId, { status: 'error', content: 'Retry could not be started.' })
    } finally { setRunning(false) }
  }

  const regenerateFinalReport = async () => {
    if (!jobId) return
    setRunning(true); setFinalLoading(true); setFinalContent(undefined)
    setQualityPassed(null); setQualityIssues([]); setError('')
    const signal = pageAbortRef.current.signal
    try {
      const base = window.API_URL ?? import.meta.env.VITE_API_URL ?? ''
      const token = localStorage.getItem('taa_token') || ''
      const response = await fetch(`${base}/api/v1/tender/analyze/${jobId}/retry/md-final`, {
        method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : undefined, signal,
      })
      await consumeAnalysisStream(response, signal)
    } catch {
      if (signal.aborted) return
      setFinalLoading(false)
      setQualityPassed(false)
      setError('The final report could not be regenerated. Please try again.')
    } finally { setRunning(false) }
  }

  const saveBid = async () => {
    if (qualityPassed === false) {
      setError('This report did not pass the quality gate. Resolve the listed issues before saving or downloading it.')
      return
    }
    setSaving(true)
    const { recommended_quote, bid_confidence } = extractSnippet(allResults)
    const bid = await createBid({
      tender_name: files.length ? `${files[0].name}${files.length > 1 ? ` +${files.length - 1} more` : ''}` : tenderText.slice(0, 100) || 'Unnamed Tender',
      recommended_quote,
      bid_confidence,
      pipeline_result: JSON.stringify(allResults),
      tender_text: tenderText,
      status: 'draft',
      tender_id: tenderId ?? undefined,
    })
    setSavedBidId(bid.id)
    setSaving(false)
  }

  const uploadRAG = async () => {
    const f = ragFileRef.current?.files?.[0]
    if (!f || !ragForm.title) return
    setUploadingRAG(true)
    const fd = new FormData()
    fd.append('file', f)
    Object.entries(ragForm).forEach(([k, v]) => fd.append(k, v))
    await uploadPastBid(fd)
    const updated = await fetchPastBids()
    setPastBids(updated)
    setRagForm({ title: '', department: '', contract_value: '', year_won: '', outcome: 'won' })
    if (ragFileRef.current) ragFileRef.current.value = ''
    setUploadingRAG(false)
  }

  // An error before any step ran (e.g. an unreadable upload) is a failed run, not a finished one.
  const failed = !running && !!error && !finalContent
  const showSteps = !failed || Object.values(agents).some(step => step.status !== 'waiting')

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      {usageLimit && <UsageLimitModal info={usageLimit} onClose={() => setUsageLimit(null)} />}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-xl font-bold text-fg">Bid Pipeline</h1>
          <p className="text-sm text-fg-subtle mt-0.5">Paste tender → full AI team analyzes → get the best quote</p>
        </div>
        <button onClick={() => setShowRAG(r => !r)}
          className="text-xs text-fg-subtle border border-edge px-3 py-1.5 rounded-lg hover:border-fg-subtle transition-colors">
          Past Bids ({pastBids.length})
        </button>
      </div>

      {/* Past Bids RAG Panel */}
      {showRAG && (
        <div className="mb-6 bg-panel border border-edge rounded-xl p-5 space-y-4">
          <div>
            <h3 className="font-semibold text-sm text-fg mb-1">Past Winning Proposals (RAG)</h3>
            <p className="text-xs text-fg-subtle">Upload past winning bids — Technical Expert AI uses them as reference to write better proposals.</p>
          </div>
          {pastBids.length > 0 && (
            <div className="space-y-2">
              {pastBids.map(p => (
                <div key={p.id} className="flex items-center gap-3 bg-sunk rounded-lg px-3 py-2">
                  <FileText className="w-4 h-4 text-fg-subtle flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-fg truncate">{p.title}</p>
                    <p className="text-xs text-fg-subtle">{p.department} · ₹{p.contract_value} · {p.year_won} · {(p.text_length / 1000).toFixed(1)}K chars</p>
                  </div>
                  <span className="text-xs bg-green-500/15 text-green-700 dark:text-green-300 px-2 py-0.5 rounded-full">{p.outcome}</span>
                  <button onClick={async () => { await deletePastBid(p.id); setPastBids(await fetchPastBids()) }} className="text-edge-strong hover:text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              ))}
            </div>
          )}
          <div className="border-t border-edge pt-4 space-y-3">
            <p className="text-xs font-medium text-fg-muted">Upload a past winning proposal</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <input value={ragForm.title} onChange={e => setRagForm(f => ({ ...f, title: e.target.value }))} placeholder="Project title *" className="text-sm border border-edge rounded-lg px-2.5 py-2 outline-none focus:border-fg-subtle col-span-2" />
              <input value={ragForm.department} onChange={e => setRagForm(f => ({ ...f, department: e.target.value }))} placeholder="Department" className="text-sm border border-edge rounded-lg px-2.5 py-2 outline-none focus:border-fg-subtle" />
              <input value={ragForm.contract_value} onChange={e => setRagForm(f => ({ ...f, contract_value: e.target.value }))} placeholder="Value (₹)" className="text-sm border border-edge rounded-lg px-2.5 py-2 outline-none focus:border-fg-subtle" />
              <input value={ragForm.year_won} onChange={e => setRagForm(f => ({ ...f, year_won: e.target.value }))} placeholder="Year" className="text-sm border border-edge rounded-lg px-2.5 py-2 outline-none focus:border-fg-subtle" />
              <select value={ragForm.outcome} onChange={e => setRagForm(f => ({ ...f, outcome: e.target.value }))} className="text-sm border border-edge rounded-lg px-2.5 py-2 outline-none focus:border-fg-subtle bg-panel">
                <option value="won">Won</option>
                <option value="submitted">Submitted</option>
              </select>
              <div className="col-span-2 flex gap-2">
                <input ref={ragFileRef} type="file" accept=".pdf,.txt,.doc,.docx" className="flex-1 text-xs file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-sunk file:text-fg-muted" />
                <button onClick={uploadRAG} disabled={uploadingRAG} className="px-3 py-2 bg-fg text-canvas text-xs rounded-lg hover:bg-fg/85 disabled:opacity-50 flex items-center gap-1.5">
                  {uploadingRAG ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />} Add
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tender history: versions, documents, re-analyse (shown above the form or the results) */}
      {tenderId && <TenderHistoryPanel tenderId={tenderId} activeJobId={jobId} defaultKind="pipeline" />}

      {/* Input Section */}
      {!started && (
        <div className="space-y-4">
          <div className="bg-saffron-500/[.08] border border-saffron-500/20 rounded-xl p-4">
            <label className="block text-xs font-semibold text-fg-muted uppercase tracking-wide mb-2">Company fit evaluation</label>
            <select value={companyMode} onChange={e => setCompanyMode(e.target.value)}
              className="w-full text-sm border border-saffron-500/30 bg-panel rounded-lg px-3 py-2.5 outline-none focus:border-saffron-500">
              {companies.length > 1 && <option value="all">Compare all {companies.length} companies and recommend the best fit</option>}
              {companies.map((company, index) => (
                <option key={company.id} value={String(company.id)}>{company.company_name || `Company ${index + 1}`}</option>
              ))}
            </select>
            <p className="text-xs text-fg-subtle mt-2">
              {companyMode === 'all'
                ? 'The AI team will compare eligibility, experience, financial capacity, certifications and tender fit, then identify the strongest company and explain why it should bid.'
                : companies.length > 1
                  ? 'Choose “Compare all companies” above to find which of your companies is the best fit for this tender.'
                  : 'This company will be evaluated against the tender requirements, with strengths, gaps and a bid recommendation.'}
            </p>
          </div>
          <div>
            <label className="block text-xs font-semibold text-fg-subtle uppercase tracking-wide mb-2">Paste Tender Details</label>
            <textarea value={tenderText} onChange={e => setTenderText(e.target.value)}
              placeholder={`Paste the full tender text here — title, scope, eligibility, technical specs, EMD amount, deadline, T&C…\n\nThe more detail you provide, the more accurate your team's analysis will be.`}
              rows={12} className="w-full text-sm border border-edge rounded-xl px-4 py-3.5 outline-none focus:border-fg-subtle transition-colors resize-none leading-relaxed" />
          </div>
          <div className="flex items-center gap-3"><div className="flex-1 h-px bg-edge" /><span className="text-xs text-fg-subtle font-medium">OR</span><div className="flex-1 h-px bg-edge" /></div>
          <div onClick={() => fileRef.current?.click()} onDrop={e => { e.preventDefault(); const dropped = Array.from(e.dataTransfer.files); if (dropped.length) setFiles(current => [...current, ...dropped].slice(0, 10)) }} onDragOver={e => e.preventDefault()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${files.length ? 'border-fg-subtle bg-sunk' : 'border-edge hover:border-fg-subtle hover:bg-sunk'}`}>
            {files.length ? (
              <div className="space-y-2 text-left">
                <p className="text-xs font-semibold text-fg-muted text-center mb-3">{files.length} document{files.length === 1 ? '' : 's'} selected</p>
                {files.map((file, index) => (
                  <div key={`${file.name}-${file.size}-${index}`} className="flex items-center gap-3 bg-panel border border-edge rounded-lg px-3 py-2">
                    <FileText className="w-5 h-5 text-accent2 flex-shrink-0" />
                    <div className="min-w-0 flex-1"><p className="font-medium text-fg text-sm truncate">{file.name}</p><p className="text-xs text-fg-subtle">{(file.size / 1024).toFixed(0)} KB</p></div>
                    <button type="button" aria-label={`Remove ${file.name}`} onClick={e => { e.stopPropagation(); setFiles(current => current.filter((_, i) => i !== index)) }} className="text-fg-subtle hover:text-red-500 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                <p className="text-xs text-accent2 text-center pt-1">Click or drop more files · maximum 10</p>
              </div>
            ) : (<><Upload className="w-7 h-7 text-edge-strong mx-auto mb-2" /><p className="text-sm text-fg-subtle">Upload tender documents</p><p className="text-xs text-fg-subtle mt-1">{TENDER_UPLOAD_HINT}</p></>)}
            <input ref={fileRef} type="file" multiple accept={TENDER_UPLOAD_ACCEPT} className="hidden" onChange={e => { const selected = Array.from(e.target.files ?? []); if (selected.length) setFiles(current => [...current, ...selected].slice(0, 10)); e.target.value = '' }} />
          </div>
          {error && <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-500/10 px-4 py-3 rounded-xl"><AlertCircle className="w-4 h-4 flex-shrink-0" />{error}</div>}
          {warning && (
            <div className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 px-4 py-3 rounded-xl">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{warning}</span>
            </div>
          )}
          <button onClick={analyze} className="w-full py-3.5 bg-fg text-canvas font-semibold rounded-xl hover:bg-fg/85 transition-colors flex items-center justify-center gap-2.5 text-sm">
            <Play className="w-4 h-4" /> Analyze with Full AI Team
          </button>
          <div className="flex items-center justify-center gap-2 flex-wrap pt-1">
            {PIPELINE_AGENTS.map((a, i) => (
              <span key={a.id} className="flex items-center gap-1.5 text-xs text-fg-subtle">
                <span className="w-4 h-4 rounded-full bg-sunk text-fg-subtle flex items-center justify-center text-[10px] font-bold">{i + 1}</span>
                {a.name.replace(' AI', '')}{i < PIPELINE_AGENTS.length - 1 && <span className="text-edge-strong">→</span>}
              </span>
            ))}
            <span className="text-edge-strong">→</span><span className="text-xs font-semibold text-fg-muted">Final Quote</span>
          </div>
        </div>
      )}

      {/* Results */}
      {started && (
        <div ref={resultsRef} className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-fg">{running ? 'Your team is analyzing the tender…' : stopped ? 'Analysis stopped' : failed ? 'Analysis could not run' : 'Analysis Complete'}</h2>
              <p className="text-xs text-fg-subtle mt-0.5">{files.length ? `${files.length} document${files.length === 1 ? '' : 's'}: ${files.map(f => f.name).join(', ')}` : `${tenderText.slice(0, 60)}…`}</p>
            </div>
            {running && (
              <button onClick={stopAnalysis} disabled={!jobId || stopping}
                className="flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-panel px-3 py-2 text-xs font-semibold text-red-700 dark:text-red-300 transition-colors hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50">
                {stopping ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5 fill-current" />}
                {stopping ? 'Stopping…' : jobId ? 'Stop analysis' : 'Preparing…'}
              </button>
            )}
            {!running && (
              <div className="flex items-center gap-2">
                {finalContent && qualityPassed !== false && !savedBidId && (
                  <button onClick={saveBid} disabled={saving} className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors">
                    {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />} Save to Bid Tracker
                  </button>
                )}
                {savedBidId && (
                  <>
                    <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400 font-medium"><CheckCircle className="w-3.5 h-3.5" /> Saved</span>
                    <button onClick={() => downloadBidPdf(savedBidId, `Bid_${savedBidId}_Summary.pdf`).catch(() => alert('Download failed.'))} title="1–2 page summary: decision, deadlines, gaps, risks, next steps" className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 bg-fg text-canvas rounded-lg hover:bg-fg/85 transition-colors">
                      <Download className="w-3 h-3" /> Download summary
                    </button>
                    <button onClick={() => downloadBidPdf(savedBidId, `Bid_${savedBidId}_Full.pdf`, true).catch(() => alert('Download failed.'))} title="Summary plus every specialist's detailed report" className="text-xs font-medium text-fg-muted underline-offset-2 hover:text-fg hover:underline">
                      Full report
                    </button>
                  </>
                )}
                <button onClick={reset} className="flex items-center gap-1.5 text-xs text-fg-subtle hover:text-fg border border-edge rounded-lg px-3 py-1.5 hover:border-fg-subtle transition-colors">
                  <RotateCcw className="w-3 h-3" /> New Tender
                </button>
              </div>
            )}
          </div>

          {error && (
            <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-500/40 bg-red-500/10 px-5 py-4 text-sm text-red-800 dark:text-red-300">
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
              <div>
                <p className="font-semibold">{failed ? 'The analysis could not run' : 'Something went wrong'}</p>
                <p className="mt-1 whitespace-pre-line text-red-800 dark:text-red-300">{error}</p>
                {failed && <p className="mt-2 text-xs text-red-700 dark:text-red-300">Fix the file or paste the tender text, then click New Tender to try again.</p>}
              </div>
            </div>
          )}

          {showSteps && (
            <div className="space-y-3">
              {PIPELINE_AGENTS.map((a, i) => (
                <AgentStepCard key={a.id} agentId={a.id} agentName={a.name} iconType={a.icon}
                  status={agents[a.id]?.status ?? 'waiting'} content={agents[a.id]?.content} stepNumber={i + 1}
                  onRetry={() => retryAgent(a.id)} />
              ))}
            </div>
          )}

          {(finalLoading || finalContent) && <FinalQuoteCard loading={finalLoading} content={finalContent} />}

          {qualityPassed === false && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-800 dark:text-red-300">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <div>
                  <p className="font-semibold">Quality review required — save and PDF export are blocked</p>
                  <p className="mt-1 text-red-800 dark:text-red-300">The generated report still contains evidence or consistency problems after automatic correction.</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {qualityIssues.map((issue, index) => <li key={`${issue.code ?? 'issue'}-${index}`}>{issue.message}</li>)}
                  </ul>
                  <button onClick={regenerateFinalReport} disabled={!jobId || running}
                    className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-panel px-3 py-2 text-xs font-semibold text-red-800 dark:text-red-300 transition-colors hover:bg-red-500/15 disabled:cursor-not-allowed disabled:opacity-50">
                    {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                    {running ? 'Regenerating…' : 'Regenerate final report'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {qualityPassed === true && finalContent && (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-green-500/30 bg-green-500/10 px-4 py-3 text-sm text-green-800 dark:text-green-300">
              <span className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 flex-shrink-0" />
                Automated evidence and consistency checks passed. Human approval is still required before bid submission.
              </span>
              <button onClick={regenerateFinalReport} disabled={!jobId || running}
                className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-green-500/40 bg-panel px-3 py-1.5 text-xs font-semibold text-green-800 dark:text-green-300 transition-colors hover:bg-green-500/15 disabled:cursor-not-allowed disabled:opacity-50">
                <RotateCcw className="h-3.5 w-3.5" /> Recheck report
              </button>
            </div>
          )}

          {finalContent && qualityPassed !== false && !savedBidId && (
            <div className="flex justify-center">
              <button onClick={saveBid} disabled={saving} className="flex items-center gap-2 px-6 py-3 bg-fg text-canvas font-medium rounded-xl hover:bg-fg/85 disabled:opacity-50 transition-colors text-sm">
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {saving ? 'Saving…' : 'Save Bid + Download PDF'}
              </button>
            </div>
          )}

          {finalContent && (
            <DiscussionPanel
              kind="pipeline"
              tenderText={tenderText || files.map(file => file.name).join(', ')}
              analysisResults={allResults}
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
