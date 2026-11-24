import { useState, useRef, useEffect, FormEvent, KeyboardEvent } from 'react'
import { Send, Loader2, MessageSquareText, Sparkles, AlertCircle, Crown } from 'lucide-react'
import { sendDiscussion, fetchTenderDiscussion, fetchJobDiscussion, DiscussionMessage } from '../../api/discussion'
import { MarkdownReport } from '../tender/MarkdownReport'

interface Props {
  kind: 'pipeline' | 'roadmap'
  tenderText: string
  analysisResults: Record<string, string>
  finalBriefing: string
  tenderId?: number | null
  jobId?: string | null
}

function versionDividerLabel(m: DiscussionMessage): string | null {
  if (m.version_number == null && !m.version_label) return null
  const parts: string[] = []
  if (m.version_number != null) parts.push(`v${m.version_number}`)
  if (m.version_label) parts.push(m.version_label)
  return parts.join(' · ')
}

const QUICK_PROMPTS: Record<'pipeline' | 'roadmap', string[]> = {
  pipeline: [
    'Reduce the quote by 5% — what changes?',
    'What if the eligibility check fails?',
    'Tighten the methodology — make it shorter',
    'Which agent\'s output is the weakest link?',
    'What are the top 3 risks I should mention to my MD?',
  ],
  roadmap: [
    'Make the recommended quote more aggressive — what\'s the risk?',
    'What if Phase 2 Qualify came back NO-BID — what then?',
    'Which phase has the highest execution risk?',
    'Summarise the action items in one paragraph',
    'How would the analysis change if our turnover was lower?',
  ],
}

export function DiscussionPanel({ kind, tenderText, analysisResults, finalBriefing, tenderId, jobId }: Props) {
  const [messages, setMessages] = useState<DiscussionMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  // Load the existing thread when tenderId/jobId are known, or reset to empty
  // (today's behaviour) when neither is present. Guard against stale loads
  // if tenderId/jobId change again before the request resolves.
  useEffect(() => {
    let cancelled = false
    setError('')
    if (tenderId != null) {
      setLoading(true)
      fetchTenderDiscussion(tenderId)
        .then(r => { if (!cancelled) setMessages(r.messages) })
        .catch(() => { if (!cancelled) setError('Could not load the chat history.') })
        .finally(() => { if (!cancelled) setLoading(false) })
    } else if (jobId) {
      setLoading(true)
      fetchJobDiscussion(jobId)
        .then(r => { if (!cancelled) setMessages(r.messages) })
        .catch(() => { if (!cancelled) setError('Could not load the chat history.') })
        .finally(() => { if (!cancelled) setLoading(false) })
    } else {
      setMessages([])
    }
    return () => { cancelled = true }
  }, [tenderId, jobId])

  const send = async (text: string) => {
    const question = text.trim()
    if (!question || busy) return
    setError('')
    // Newly sent messages carry the current version's info (looked up from
    // the last loaded message with the same job_id) so the divider logic
    // stays consistent as the thread grows.
    const lastSameJob = jobId ? [...messages].reverse().find(m => m.job_id === jobId) : undefined
    const userMsg: DiscussionMessage = {
      role: 'user',
      content: question,
      ...(jobId ? { job_id: jobId, version_number: lastSameJob?.version_number, version_label: lastSameJob?.version_label } : {}),
    }
    const newHistory = [...messages, userMsg]
    setMessages(newHistory)
    setInput('')
    setBusy(true)
    try {
      const r = await sendDiscussion({
        kind,
        tender_text: tenderText,
        analysis_results: analysisResults,
        final_briefing: finalBriefing,
        ...(jobId ? { job_id: jobId } : { history: messages }),   // previous turns (without the new question)
        question,
      })
      const assistantMsg: DiscussionMessage = {
        role: 'assistant',
        content: r.reply,
        ...(jobId ? { job_id: jobId, version_number: lastSameJob?.version_number, version_label: lastSameJob?.version_label } : {}),
      }
      setMessages([...newHistory, assistantMsg])
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Discussion failed. Try again in a moment.')
      // remove the optimistic user message so they can retry
      setMessages(messages)
    } finally {
      setBusy(false)
      textareaRef.current?.focus()
    }
  }

  const onSubmit = (e: FormEvent) => { e.preventDefault(); send(input) }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) }
  }

  return (
    <section className="mt-10 bg-panel border border-ink-200 rounded-2xl overflow-hidden">
      {/* === Header === */}
      <div className="on-dark bg-gradient-to-br from-navy-900 to-navy-800 text-cream-100 px-6 py-5 relative overflow-hidden">
        <div className="absolute inset-0 bg-dotgrid-light pointer-events-none opacity-40" />
        <div className="relative flex items-start gap-4">
          <div className="w-11 h-11 rounded-xl bg-cream-100/10 backdrop-blur flex items-center justify-center flex-shrink-0">
            <MessageSquareText className="w-5 h-5 text-cream-100" />
          </div>
          <div className="flex-1">
            <p className="eyebrow text-cream-200">Discuss with the team</p>
            <h3 className="mt-1 font-display text-2xl text-cream-100 leading-tight">Have a question about this analysis?</h3>
            <p className="mt-1.5 text-sm text-cream-100/70">
              Ask follow-ups, debate the numbers, request alternatives. The Managing Director synthesiser has full context of every team output.
            </p>
          </div>
          <div className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono tracking-widest text-cream-200/80 bg-cream-100/10 px-2 py-1 rounded-full border border-cream-100/15">
            <Crown className="w-3 h-3" /> MD CONTEXT
          </div>
        </div>
      </div>

      {/* === Body === */}
      <div className="bg-cream-50">
        {/* Quick-suggest chips (only shown when no messages yet) */}
        {!loading && messages.length === 0 && (
          <div className="px-6 pt-6">
            <p className="eyebrow text-ink-500 mb-3 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" /> Try one of these
            </p>
            <div className="flex flex-wrap gap-2">
              {QUICK_PROMPTS[kind].map((p, i) => (
                <button
                  key={i}
                  onClick={() => send(p)}
                  disabled={busy}
                  className="text-xs px-3 py-1.5 rounded-full bg-panel border border-ink-200 text-ink-700 hover:bg-ink-100 hover:border-ink-400 transition disabled:opacity-50"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message thread */}
        {loading && (
          <div className="px-6 pt-5 pb-3 flex items-center gap-2 text-sm text-ink-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading conversation…
          </div>
        )}
        {!loading && (messages.length > 0 || busy) && (
          <div className="px-6 pt-5 pb-3 max-h-[520px] overflow-y-auto scrollbar-thin space-y-4">
            {messages.map((m, i) => {
              const prevLabel = i > 0 ? versionDividerLabel(messages[i - 1]) : null
              const label = versionDividerLabel(m)
              const showDivider = label !== null && label !== prevLabel
              return (
                <div key={i}>
                  {showDivider && (
                    <div className="flex items-center gap-3 my-2 text-[11px] font-mono tracking-wide text-ink-400">
                      <span className="flex-1 h-px bg-ink-200" />
                      <span>— {label} —</span>
                      <span className="flex-1 h-px bg-ink-200" />
                    </div>
                  )}
                  <Bubble role={m.role} content={m.content} />
                </div>
              )
            })}
            {busy && <Bubble role="assistant" loading />}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mx-6 mt-2 mb-2 flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2.5 rounded-lg">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />{error}
          </div>
        )}

        {/* Composer */}
        <form onSubmit={onSubmit} className="border-t border-ink-200 bg-panel px-4 py-3 flex items-end gap-2">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            disabled={busy}
            placeholder="Ask a follow-up, debate a number, request an alternative…"
            className="flex-1 resize-none px-3.5 py-2.5 text-sm bg-cream-50 border border-ink-200 rounded-lg focus:bg-panel focus:border-ink-800 focus:ring-2 focus:ring-ink-100 outline-none transition placeholder-ink-400"
            style={{ minHeight: 42, maxHeight: 200 }}
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="px-4 h-[42px] bg-ink-900 hover:bg-ink-700 disabled:bg-ink-300 text-white font-semibold rounded-lg text-sm flex items-center justify-center gap-1.5 transition shadow-md shadow-ink-900/15 flex-shrink-0"
            aria-label="Send"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </form>
        <p className="text-[11px] text-ink-400 text-center pb-3 px-4">
          Discussion messages don't count toward your plan limit · Enter to send · Shift+Enter for new line
        </p>
      </div>
    </section>
  )
}

function Bubble({ role, content, loading = false }: { role: 'user' | 'assistant'; content?: string; loading?: boolean }) {
  const isUser = role === 'user'
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
        isUser ? 'bg-ink-700 text-cream-100' : 'bg-cream-200 text-ink-900 border border-ink-300'
      }`}>
        {isUser ? 'You' : 'MD'}
      </div>
      <div className={`rounded-2xl ${
        isUser ? 'max-w-[80%] px-4 py-2.5 bg-ink-900 text-cream-100 rounded-tr-sm' : 'max-w-[92%] px-5 py-3 bg-panel border border-ink-200 rounded-tl-sm'
      }`}>
        {loading ? (
          <div className="flex items-center gap-2 text-ink-500">
            <span className="flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-ink-400 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-ink-400 animate-bounce" style={{ animationDelay: '120ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-ink-400 animate-bounce" style={{ animationDelay: '240ms' }} />
            </span>
            <span className="text-xs">Thinking…</span>
          </div>
        ) : isUser ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
        ) : (
          <MarkdownReport content={content || ''} />
        )}
      </div>
    </div>
  )
}

