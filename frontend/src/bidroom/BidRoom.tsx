import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import {
  Search, HelpCircle, Sun, Moon, Menu, Users, Send, Paperclip,
  ThumbsUp, ThumbsDown, Copy, FileText, X, ChevronLeft, Sparkles,
  LayoutDashboard, Briefcase, BadgeIndianRupee, Scale,
  Settings2, FolderCheck,
} from 'lucide-react'
import { useTheme } from '../theme/ThemeContext'
import { bidRoomAgents, agentById, channels, BidRoomAgent, BidRoomAgentId, Channel } from './agents'
import { routeMessage, parseMention } from './router'
import { runTurn, ChatTurn } from './orchestrator'
import { Sigil } from './Sigil'
import { api } from '../api/client'
import './bidroom.css'
import { CHAT_UPLOAD_ACCEPT } from '../utils/uploadTypes'

type MsgKind = 'user' | 'agent' | 'recommendation'

const CHANNEL_ICONS = {
  general: LayoutDashboard,
  bids: Briefcase,
  pricing: BadgeIndianRupee,
  legal: Scale,
  technical: Settings2,
  docs: FolderCheck,
} as const
interface Msg {
  id: number
  kind: MsgKind
  agentId?: BidRoomAgentId
  content: string
  routingReason?: string
  contributors?: BidRoomAgentId[]
  streaming?: boolean
  error?: boolean
  feedback?: 'up' | 'down' | null
}

interface AttachedDocument { name: string; text: string; characters: number }

export function BidRoom({ embedded = false }: { embedded?: boolean }) {
  const { resolved, toggle } = useTheme()
  const [channelId, setChannelId] = useState('general')
  const [byChannel, setByChannel] = useState<Record<string, Msg[]>>({})
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [tender, setTender] = useState('')
  const [documents, setDocuments] = useState<AttachedDocument[]>([])
  const [uploadingDocuments, setUploadingDocuments] = useState(false)
  const [documentError, setDocumentError] = useState('')
  const [showTender, setShowTender] = useState(false)
  const [rosterOpen, setRosterOpen] = useState(false)
  const [channelsOpen, setChannelsOpen] = useState(false)
  const [mentionOpen, setMentionOpen] = useState(false)
  const [demoMode, setDemoMode] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [showHelp, setShowHelp] = useState(false)

  const idRef = useRef(1)
  const nextId = () => idRef.current++
  const listRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const documentInputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const channel = useMemo<Channel>(() => channels.find((c) => c.id === channelId) ?? channels[0], [channelId])
  const messages = byChannel[channelId] ?? []
  const sharedContext = useMemo(() => [
    tender.trim() ? `--- PASTED TENDER CONTEXT ---\n${tender.trim()}` : '',
    ...documents.map((d) => `--- ATTACHED DOCUMENT: ${d.name} ---\n${d.text}`),
  ].filter(Boolean).join('\n\n'), [tender, documents])

  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // ⌘K / Ctrl-K opens the search palette; Esc closes any open header modal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setShowSearch((v) => !v); setShowHelp(false) }
      else if (e.key === 'Escape') { setShowSearch(false); setShowHelp(false) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const patch = useCallback((cid: string, id: number, fn: (m: Msg) => Msg) => {
    setByChannel((prev) => ({
      ...prev,
      [cid]: (prev[cid] ?? []).map((m) => (m.id === id ? fn(m) : m)),
    }))
  }, [])
  const append = useCallback((cid: string, msg: Msg) => {
    setByChannel((prev) => ({ ...prev, [cid]: [...(prev[cid] ?? []), msg] }))
  }, [])

  const send = useCallback(
    async (raw?: string) => {
      const text = (raw ?? input).trim()
      if (!text || busy) return
      const cid = channelId

      // optimistic user bubble
      const historyBefore: ChatTurn[] = (byChannel[cid] ?? [])
        .filter((m) => m.kind !== 'recommendation')
        .map((m) => ({ role: m.kind === 'user' ? 'user' : 'agent', agentId: m.agentId, content: m.content }))
      append(cid, { id: nextId(), kind: 'user', content: text })
      setInput('')
      setMentionOpen(false)
      setBusy(true)

      const route = routeMessage(text, channel)
      const ctrl = new AbortController()
      abortRef.current = ctrl

      // one bubble per routed agent, created on start
      const bubbleFor: Partial<Record<BidRoomAgentId, number>> = {}

      try {
        await runTurn({
          userText: text,
          route,
          history: historyBefore,
          tenderContext: sharedContext,
          signal: ctrl.signal,
          events: {
            onAgentStart: (id) => {
              const mid = nextId()
              bubbleFor[id] = mid
              append(cid, { id: mid, kind: 'agent', agentId: id, content: '', streaming: true, routingReason: route.reason })
            },
            onToken: (id, chunk) => {
              const mid = bubbleFor[id]
              if (mid != null) patch(cid, mid, (m) => ({ ...m, content: m.content + chunk }))
            },
            onAgentComplete: (id, full) => {
              const mid = bubbleFor[id]
              if (mid != null) patch(cid, mid, (m) => ({ ...m, content: full, streaming: false }))
            },
            onAgentError: (id, message) => {
              const mid = bubbleFor[id]
              if (mid != null) patch(cid, mid, (m) => ({ ...m, content: message, streaming: false, error: true }))
              else append(cid, { id: nextId(), kind: 'agent', agentId: id, content: message, error: true })
            },
            onRecommendation: (recText, contributors) => {
              append(cid, { id: nextId(), kind: 'recommendation', content: recText, contributors })
            },
            onDemo: () => setDemoMode(true),
          },
        })
      } finally {
        setBusy(false)
        abortRef.current = null
      }
    },
    [input, busy, channelId, byChannel, channel, sharedContext, append, patch],
  )

  const uploadDocuments = async (selected: File[]) => {
    if (!selected.length) return
    if (documents.length + selected.length > 5) {
      setDocumentError('You can attach up to 5 documents to one chat workspace.')
      return
    }
    setUploadingDocuments(true)
    setDocumentError('')
    try {
      const fd = new FormData()
      selected.forEach((file) => fd.append('files', file))
      const response = await api.post('/api/v1/chat/extract-documents', fd)
      setDocuments((current) => [...current, ...(response.data.documents as AttachedDocument[])])
    } catch (error: any) {
      setDocumentError(error?.response?.data?.detail || 'Could not read the selected document.')
    } finally {
      setUploadingDocuments(false)
      if (documentInputRef.current) documentInputRef.current.value = ''
    }
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }
  const onInput = (v: string) => {
    setInput(v)
    const el = taRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 150) + 'px'
    }
    // open mention popover when the token under the cursor starts with @
    const m = v.match(/@([a-z-]*)$/i)
    setMentionOpen(!!m)
  }
  const insertMention = (a: BidRoomAgent) => {
    setInput((v) => v.replace(/@([a-z-]*)$/i, `@${a.name} `))
    setMentionOpen(false)
    taRef.current?.focus()
  }

  const S = STYLES
  const mentionMatches = mentionOpen
    ? bidRoomAgents.filter((a) => {
        const q = (input.match(/@([a-z-]*)$/i)?.[1] ?? '').toLowerCase()
        return a.name.toLowerCase().includes(q) || a.id.includes(q)
      })
    : []

  return (
    <div className={`bidroom br-scroll${embedded ? ' bidroom--embedded' : ''}`} style={S.root}>
      {/* ── TOP BAR ─────────────────────────────────────────────── */}
      <header style={S.topbar}>
        <div style={S.topLeft}>
          <button
            className="br-focusable br-channels-toggle"
            style={S.iconBtn}
            onClick={() => setChannelsOpen((v) => !v)}
            aria-label="Toggle channels"
          >
            <Menu size={18} />
          </button>
          <div style={S.brandMark} aria-hidden><Sparkles size={18} /></div>
          <div style={S.brandCopy}>
            <span className="br-h3" style={{ fontFamily: 'var(--font-display)' }}>{embedded ? 'AI Bid Team' : 'The Bid Room'}</span>
            <span className="br-caption" style={{ color: 'var(--text-subtle)' }}>Tender intelligence workspace</span>
          </div>
          <span style={S.wsChip} className="br-mono">{tender ? 'Tender context active' : 'Ready for a tender'}</span>
          {demoMode && (
            <span style={S.demoChip} className="br-caption" title="Backend /api/v1/chat is unreachable or has no LLM provider key — replies are served by the built-in demo responder.">
              Demo mode
            </span>
          )}
        </div>
        <div style={S.topRight}>
          <button
            type="button"
            className="br-focusable"
            style={{ ...S.searchBox, cursor: 'pointer' }}
            onClick={() => setShowSearch(true)}
            aria-label="Search — jump to a channel, agent or message"
          >
            <Search size={15} style={{ color: 'var(--text-subtle)' }} />
            <span className="br-caption" style={{ color: 'var(--text-subtle)' }}>Search</span>
            <kbd style={S.kbd}>⌘K</kbd>
          </button>
          <button className="br-focusable" style={S.iconBtn} onClick={() => setShowHelp(true)} aria-label="Help"><HelpCircle size={18} /></button>
          <button className="br-focusable" style={S.iconBtn} onClick={toggle} aria-label="Toggle theme">
            {resolved === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button
            className="br-focusable br-roster-toggle"
            style={S.iconBtn}
            onClick={() => setRosterOpen((v) => !v)}
            aria-label="Toggle team roster"
          >
            <Users size={18} />
          </button>
          <span className="br-status"><span className="br-presence-dot" />12 specialists ready</span>
          {!embedded && <div style={S.userAvatar} aria-hidden>U</div>}
        </div>
      </header>

      {/* ── BODY ────────────────────────────────────────────────── */}
      <div style={S.body}>
        {/* CHANNELS */}
        <nav style={S.channels} className={`br-scroll br-channels${channelsOpen ? ' br-open' : ''}`}>
          <div style={S.channelsHead}>
            <span className="br-caption" style={{ color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '.12em' }}>Bid workstreams</span>
            <button style={S.iconBtn} className="br-channels-toggle" onClick={() => setChannelsOpen(false)} aria-label="Close channels"><ChevronLeft size={16} /></button>
          </div>
          {channels.map((c) => {
            const active = c.id === channelId
            const ChannelIcon = CHANNEL_ICONS[c.id as keyof typeof CHANNEL_ICONS] ?? LayoutDashboard
            return (
              <button
                key={c.id}
                className="br-focusable br-channel-item"
                onClick={() => { setChannelId(c.id); setChannelsOpen(false) }}
                style={{ ...S.channelItem, ...(active ? S.channelActive : null) }}
              >
                <ChannelIcon size={16} strokeWidth={1.9} />
                <span className="br-body" style={{ fontWeight: active ? 600 : 500 }}>{c.name}</span>
              </button>
            )
          })}
          <button style={S.tenderBtn} className="br-focusable" onClick={() => setShowTender(true)}>
            <FileText size={15} />
            <span className="br-label">{tender ? 'Tender attached' : 'Add tender context'}</span>
            {tender && <span style={S.readyDot} />}
          </button>
        </nav>

        {/* CHAT */}
        <main style={S.chat}>
          <div style={S.channelHeader}>
            <span className="br-strong">{channel.name} workspace</span>
            <span className="br-caption" style={{ color: 'var(--text-subtle)' }}>{channel.hint}</span>
          </div>

          <div ref={listRef} style={S.messageList} className="br-scroll">
            {messages.length === 0 ? (
              <EmptyState channel={channel} onChip={(c) => send(c)} tender={sharedContext} onTender={() => setShowTender(true)} />
            ) : (
              messages.map((m) => (
                <MessageRow key={m.id} m={m} onFeedback={(f) => patch(channelId, m.id, (x) => ({ ...x, feedback: x.feedback === f ? null : f }))} />
              ))
            )}
          </div>

          {/* COMPOSER */}
          <div style={S.composerWrap}>
            {(documents.length > 0 || documentError) && (
              <div className="br-attachments">
                {documents.map((document, index) => (
                  <span className="br-attachment" key={`${document.name}-${index}`} title={`${document.characters.toLocaleString()} readable characters`}>
                    <FileText size={13} />
                    <span>{document.name}</span>
                    <button onClick={() => setDocuments((items) => items.filter((_, i) => i !== index))} aria-label={`Remove ${document.name}`}><X size={12} /></button>
                  </span>
                ))}
                {uploadingDocuments && <span className="br-attachment br-attachment-loading">Reading documents…</span>}
                {documentError && <span className="br-document-error">{documentError}</span>}
              </div>
            )}
            {mentionOpen && mentionMatches.length > 0 && (
              <div style={S.mentionPop} className="br-scroll">
                {mentionMatches.map((a) => (
                  <button key={a.id} style={S.mentionItem} className="br-focusable" onClick={() => insertMention(a)}>
                    <Sigil agent={a} size={22} />
                    <span className="br-label">{a.name}</span>
                    <span className="br-caption" style={{ color: 'var(--text-subtle)' }}>{a.role}</span>
                  </button>
                ))}
              </div>
            )}
            <div style={S.composer} className="br-composer">
              <button style={S.iconBtn} className="br-focusable" aria-label="Attach documents" disabled={uploadingDocuments} onClick={() => documentInputRef.current?.click()}>
                <Paperclip size={18} />
              </button>
              <input ref={documentInputRef} type="file" multiple accept={CHAT_UPLOAD_ACCEPT} className="hidden" onChange={(e) => uploadDocuments(Array.from(e.target.files ?? []))} />
              <textarea
                ref={taRef}
                value={input}
                onChange={(e) => onInput(e.target.value)}
                onKeyDown={onKey}
                rows={1}
                placeholder={`Message ${channel.name}…  (type @ to address an agent)`}
                style={S.textarea}
                className="br-scroll br-focusable"
              />
              <button
                onClick={() => send()}
                disabled={!input.trim() || busy}
                className="br-focusable"
                style={{ ...S.sendBtn, ...(!input.trim() || busy ? S.sendDisabled : null) }}
                aria-label="Send message"
              >
                <Send size={16} />
              </button>
            </div>
            <p className="br-caption" style={{ textAlign: 'center', color: 'var(--text-subtle)', marginTop: 6 }}>
              Enter to send · Shift+Enter for a new line · Legal & QA replies are assistive, not sign-off
            </p>
          </div>
        </main>

        {/* ROSTER */}
        <aside style={S.roster} className={`br-scroll br-roster${rosterOpen ? ' br-open' : ''}`}>
          <div style={S.channelsHead}>
            <span className="br-caption" style={{ color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '.12em' }}>Specialist roster</span>
            <button style={S.iconBtn} className="br-roster-toggle" onClick={() => setRosterOpen(false)} aria-label="Close roster"><X size={16} /></button>
          </div>
          {bidRoomAgents.map((a) => (
            <button
              key={a.id}
              className="br-focusable br-roster-card"
              style={S.rosterCard}
              title={a.example}
              onClick={() => { setInput((v) => `${v}@${a.name} `.trimStart()); taRef.current?.focus() }}
            >
              <Sigil agent={a} size={34} presence />
              <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, textAlign: 'left' }}>
                <span className="br-strong" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {a.name}
                  {a.assistive && <span style={S.assistiveTag} className="br-caption">assistive</span>}
                </span>
                <span className="br-caption" style={{ color: 'var(--text-subtle)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.specialty}</span>
              </span>
            </button>
          ))}
        </aside>
      </div>

      <div
        className={`br-scrim${rosterOpen || channelsOpen ? ' br-open' : ''}`}
        style={S.scrim}
        onClick={() => { setRosterOpen(false); setChannelsOpen(false) }}
      />

      {showTender && (
        <TenderModal
          value={tender}
          onClose={() => setShowTender(false)}
          onSave={(v) => { setTender(v); setShowTender(false) }}
        />
      )}

      {showSearch && (
        <SearchModal
          byChannel={byChannel}
          onClose={() => setShowSearch(false)}
          onPickChannel={(id) => { setChannelId(id); setChannelsOpen(false); setShowSearch(false) }}
          onPickAgent={(a) => {
            setInput((v) => (v.trim() ? v.trimEnd() + ' ' : '') + '@' + a.name + ' ')
            setShowSearch(false)
            setTimeout(() => taRef.current?.focus(), 0)
          }}
        />
      )}

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}

/* ── message row ─────────────────────────────────────────────── */
function MessageRow({ m, onFeedback }: { m: Msg; onFeedback: (f: 'up' | 'down') => void }) {
  const S = STYLES
  if (m.kind === 'user') {
    return (
      <div className="br-msg-enter" style={S.rowUser}>
        <div style={S.userBubble} className="br-body">{m.content}</div>
      </div>
    )
  }
  if (m.kind === 'recommendation') {
    return (
      <div className="br-msg-enter" style={S.recWrap}>
        <div style={S.recBubble}>
          <div style={S.recLabel} className="br-caption">
            <Sparkles size={13} /> Team recommendation
            {m.contributors && (
              <span style={{ marginLeft: 6, color: 'var(--text-subtle)' }}>
                · {m.contributors.map((id) => agentById(id).name).join(' · ')}
              </span>
            )}
          </div>
          <div className="br-body" style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
        </div>
      </div>
    )
  }

  const a = agentById(m.agentId!)
  const solid = `var(${a.solidVar})`
  const soft = `var(${a.softVar})`
  return (
    <div className="br-msg-enter" style={S.rowAgent}>
      <Sigil agent={a} size={30} />
      <div style={{ ...S.agentBubble, borderLeft: `3px solid ${solid}` }}>
        <div style={S.agentHead}>
          <span className="br-strong">{a.name}</span>
          <span style={{ ...S.routingTag, background: soft, color: solid }} className="br-caption" title={m.routingReason}>
            responded as {a.name}
          </span>
        </div>
        <div className="br-body" style={{ whiteSpace: 'pre-wrap', color: m.error ? 'var(--danger)' : 'var(--text)' }}>
          {m.content}
          {m.streaming && (m.content ? <span className="br-caret" /> : <span className="br-typing" style={{ color: solid }}><span /><span /><span /></span>)}
        </div>
        {a.assistive && !m.streaming && !m.error && (
          <div className="br-caption" style={S.assistiveFooter}>Assistive review — not {a.id === 'legal-compliance' ? 'legal' : 'compliance'} sign-off.</div>
        )}
        {!m.streaming && !m.error && (
          <div style={S.msgActions}>
            <button style={{ ...S.msgAction, ...(m.feedback === 'up' ? S.msgActionOn : null) }} onClick={() => onFeedback('up')} aria-label="Helpful"><ThumbsUp size={13} /></button>
            <button style={{ ...S.msgAction, ...(m.feedback === 'down' ? S.msgActionOn : null) }} onClick={() => onFeedback('down')} aria-label="Not helpful"><ThumbsDown size={13} /></button>
            <button style={S.msgAction} onClick={() => navigator.clipboard?.writeText(m.content)} aria-label="Copy"><Copy size={13} /></button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── empty state ─────────────────────────────────────────────── */
function EmptyState({ channel, onChip, tender, onTender }: { channel: Channel; onChip: (c: string) => void; tender: string; onTender: () => void }) {
  const S = STYLES
  return (
    <div style={S.empty}>
      <div className="br-eyebrow">AI BID COMMAND DESK</div>
      <div style={S.emptyIcon} aria-hidden><Sparkles size={25} /></div>
      <p className="br-h2" style={{ fontFamily: 'var(--font-display)' }}>What can the team solve for you?</p>
      <p className="br-body" style={{ color: 'var(--text-muted)', maxWidth: 460, textAlign: 'center' }}>
        Ask in plain language. The right tender specialist responds automatically, while strategic questions bring multiple experts into one answer.
      </p>
      <div style={S.chips}>
        {channel.chips.map((c) => (
          <button key={c} style={S.chip} className="br-focusable br-prompt-chip" onClick={() => onChip(c)}>{c}<ChevronLeft className="br-prompt-arrow" size={14} /></button>
        ))}
      </div>
      {!tender && (
        <button style={S.tenderHint} className="br-focusable" onClick={onTender}>
          <FileText size={14} /> Tip: add your tender so agents give tender-specific answers
        </button>
      )}
    </div>
  )
}

/* ── tender modal ────────────────────────────────────────────── */
function TenderModal({ value, onClose, onSave }: { value: string; onClose: () => void; onSave: (v: string) => void }) {
  const S = STYLES
  const [v, setV] = useState(value)
  return (
    <div style={S.scrimModal} onClick={onClose}>
      <div style={S.modal} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalHead}>
          <span className="br-h3">Tender context</span>
          <button style={S.iconBtn} onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <p className="br-caption" style={{ color: 'var(--text-muted)', marginBottom: 10 }}>
          Paste the RFP / tender text or key details. Agents will ground their answers in it. Treated as reference data, never as instructions.
        </p>
        <textarea
          value={v}
          onChange={(e) => setV(e.target.value)}
          placeholder="e.g. City Rail Signaling Tender 2026 — scope, eligibility, EMD, deadline, evaluation criteria…"
          style={S.modalTa}
          className="br-scroll br-focusable"
          autoFocus
        />
        <div style={S.modalActions}>
          {value && <button style={S.btnGhost} className="br-focusable" onClick={() => onSave('')}>Remove</button>}
          <button style={S.btnGhost} className="br-focusable" onClick={onClose}>Cancel</button>
          <button style={S.btnPrimary} className="br-focusable" onClick={() => onSave(v.trim())}>Save context</button>
        </div>
      </div>
    </div>
  )
}

/* ── search palette (⌘K) ─────────────────────────────────────── */
function SearchModal({ byChannel, onClose, onPickChannel, onPickAgent }: {
  byChannel: Record<string, Msg[]>
  onClose: () => void
  onPickChannel: (id: string) => void
  onPickAgent: (a: BidRoomAgent) => void
}) {
  const S = STYLES
  const [q, setQ] = useState('')
  const query = q.trim().toLowerCase()
  const row: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 'var(--r-sm)', border: 'none', background: 'transparent', color: 'var(--text)', cursor: 'pointer', textAlign: 'left', width: '100%' }

  const chMatches = channels.filter((c) => !query || c.name.toLowerCase().includes(query) || c.id.includes(query))
  const agMatches = bidRoomAgents.filter((a) => !query || a.name.toLowerCase().includes(query) || a.role.toLowerCase().includes(query))
  const msgMatches = query
    ? Object.entries(byChannel).flatMap(([cid, msgs]) =>
        msgs.filter((m) => m.content && m.content.toLowerCase().includes(query)).map((m) => ({ cid, m }))
      ).slice(0, 8)
    : []

  return (
    <div style={S.scrimModal} onClick={onClose}>
      <div style={{ ...S.modal, maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, borderBottom: '1px solid var(--border)', paddingBottom: 10, marginBottom: 8 }}>
          <Search size={16} style={{ color: 'var(--text-subtle)' }} />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Jump to a channel, @agent, or search messages…"
            className="br-focusable" style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', color: 'var(--text)', fontSize: 15 }} />
          <button style={S.iconBtn} onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="br-scroll" style={{ maxHeight: '52vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {chMatches.length > 0 && <div className="br-caption" style={{ color: 'var(--text-subtle)', padding: '6px 6px 2px' }}>CHANNELS</div>}
          {chMatches.map((c) => (
            <button key={c.id} className="br-focusable" style={row} onClick={() => onPickChannel(c.id)}>
              <span className="br-strong">{c.name}</span>
            </button>
          ))}
          {agMatches.length > 0 && <div className="br-caption" style={{ color: 'var(--text-subtle)', padding: '8px 6px 2px' }}>AGENTS — mention in composer</div>}
          {agMatches.map((a) => (
            <button key={a.id} className="br-focusable" style={row} onClick={() => onPickAgent(a)}>
              <Sigil agent={a} size={22} />
              <span className="br-strong">{a.name}</span>
              <span className="br-caption" style={{ color: 'var(--text-subtle)', marginLeft: 'auto' }}>{a.role}</span>
            </button>
          ))}
          {msgMatches.length > 0 && <div className="br-caption" style={{ color: 'var(--text-subtle)', padding: '8px 6px 2px' }}>MESSAGES</div>}
          {msgMatches.map(({ cid, m }, i) => {
            const ch = channels.find((c) => c.id === cid)
            return (
              <button key={i} className="br-focusable" style={row} onClick={() => onPickChannel(cid)}>
                <span className="br-caption" style={{ color: 'var(--primary)', flexShrink: 0 }}>{ch?.name}</span>
                <span className="br-caption" style={{ color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.content.slice(0, 90)}</span>
              </button>
            )
          })}
          {query && chMatches.length === 0 && agMatches.length === 0 && msgMatches.length === 0 && (
            <div className="br-caption" style={{ color: 'var(--text-subtle)', padding: 14, textAlign: 'center' }}>No matches for “{q}”.</div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── help ────────────────────────────────────────────────────── */
function HelpModal({ onClose }: { onClose: () => void }) {
  const S = STYLES
  const rows: [string, string][] = [
    ['Ask in plain language', 'The right specialist auto-responds — you don’t pick who.'],
    ['@mention an agent', 'Type @Pricing, @Legal, @Finance… to address one directly.'],
    ['Strategic questions', 'Broad questions pull in up to four specialists and end with one consolidated Team recommendation.'],
    ['Channels', '#pricing, #legal, #technical… each biases routing toward that specialist.'],
    ['Add tender context', 'Paste the RFP so every answer is grounded in your tender.'],
    ['Legal & QA', 'Their replies are assistive — not a legal or compliance sign-off.'],
  ]
  return (
    <div style={S.scrimModal} onClick={onClose}>
      <div style={{ ...S.modal, maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalHead}>
          <span className="br-h3">How the Bid Room works</span>
          <button style={S.iconBtn} onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 4 }}>
          {rows.map(([t, d]) => (
            <div key={t}>
              <div className="br-strong">{t}</div>
              <div className="br-caption" style={{ color: 'var(--text-muted)', marginTop: 2 }}>{d}</div>
            </div>
          ))}
        </div>
        <div style={{ ...S.modalActions, marginTop: 16 }}>
          <button style={S.btnPrimary} className="br-focusable" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
  )
}

/* ═══ styles — tokens straight from the Design Brief ═══════════════════════ */
const STYLES: Record<string, React.CSSProperties> = {
  root: { height: '100dvh', display: 'flex', flexDirection: 'column', background: 'var(--bg)', color: 'var(--text)', overflow: 'hidden' },
  topbar: { minHeight: 68, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px', background: 'var(--surface)', borderBottom: '1px solid var(--border)', boxShadow: 'var(--shadow-sm)' },
  topLeft: { display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 },
  brandMark: { width: 36, height: 36, display: 'grid', placeItems: 'center', borderRadius: 10, color: 'var(--primary)', background: 'var(--primary-soft)', border: '1px solid color-mix(in srgb, var(--primary) 24%, transparent)' },
  brandCopy: { display: 'flex', flexDirection: 'column', minWidth: 0 },
  wsChip: { padding: '3px 8px', borderRadius: 'var(--r-pill)', background: 'var(--primary-soft)', color: 'var(--primary)', fontSize: 11 },
  demoChip: { padding: '3px 8px', borderRadius: 'var(--r-pill)', background: 'color-mix(in srgb, var(--warning) 16%, transparent)', color: 'var(--warning)', border: '1px solid color-mix(in srgb, var(--warning) 40%, transparent)', fontWeight: 600 },
  topRight: { display: 'flex', alignItems: 'center', gap: 6 },
  searchBox: { display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 'var(--r-sm)', background: 'var(--surface-2)', border: '1px solid var(--border)', cursor: 'text' },
  kbd: { fontFamily: 'var(--font-mono)', fontSize: 10, padding: '1px 5px', borderRadius: 4, background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-subtle)' },
  iconBtn: { width: 34, height: 34, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 'var(--r-sm)', border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' },
  userAvatar: { width: 30, height: 30, borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 600, marginLeft: 4 },

  body: { flex: 1, display: 'flex', minHeight: 0, position: 'relative' },

  channels: { width: 228, flexShrink: 0, background: 'var(--surface-2)', borderRight: '1px solid var(--border)', padding: 14, display: 'flex', flexDirection: 'column', gap: 4, overflowY: 'auto' },
  channelsHead: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 8px 8px' },
  channelItem: { display: 'flex', alignItems: 'center', gap: 9, height: 42, padding: '0 11px', borderRadius: 'var(--r-sm)', border: '1px solid transparent', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', textAlign: 'left', borderLeft: '3px solid transparent' },
  channelActive: { background: 'var(--primary-soft)', color: 'var(--primary)', borderColor: 'color-mix(in srgb, var(--primary) 18%, transparent)', borderLeft: '3px solid var(--primary)' },
  tenderBtn: { marginTop: 'auto', display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderRadius: 'var(--r-sm)', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-muted)', cursor: 'pointer' },
  readyDot: { width: 7, height: 7, borderRadius: '50%', background: 'var(--success)', marginLeft: 'auto' },

  chat: { flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--surface)' },
  channelHeader: { flexShrink: 0, padding: '14px 22px', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 2, background: 'color-mix(in srgb, var(--surface) 94%, var(--primary-soft))' },
  messageList: { flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 860, width: '100%', margin: '0 auto' },

  rowUser: { display: 'flex', justifyContent: 'flex-end' },
  userBubble: { maxWidth: '78%', padding: '10px 14px', background: 'var(--surface-2)', color: 'var(--text)', borderRadius: 'var(--r-md)', borderBottomRightRadius: 3, whiteSpace: 'pre-wrap' },
  rowAgent: { display: 'flex', gap: 10, alignItems: 'flex-start' },
  agentBubble: { maxWidth: '82%', minWidth: 0, padding: '10px 14px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', borderBottomLeftRadius: 3, boxShadow: 'var(--shadow-sm)' },
  agentHead: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' },
  routingTag: { padding: '1px 7px', borderRadius: 'var(--r-pill)', fontWeight: 600 },
  assistiveFooter: { marginTop: 6, color: 'var(--text-subtle)', fontStyle: 'italic' },
  msgActions: { display: 'flex', gap: 4, marginTop: 8 },
  msgAction: { width: 26, height: 26, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid transparent', background: 'transparent', color: 'var(--text-subtle)', cursor: 'pointer' },
  msgActionOn: { color: 'var(--primary)', background: 'var(--primary-soft)' },

  recWrap: { display: 'flex', paddingLeft: 40 },
  recBubble: { width: '100%', padding: '12px 16px', background: 'var(--surface)', border: '1px solid var(--border)', borderLeft: '3px solid var(--primary)', borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-md)' },
  recLabel: { display: 'flex', alignItems: 'center', gap: 5, color: 'var(--primary)', fontWeight: 600, marginBottom: 6 },

  composerWrap: { flexShrink: 0, padding: '12px 20px 14px', borderTop: '1px solid var(--border)', maxWidth: 860, width: '100%', margin: '0 auto', position: 'relative' },
  composer: { display: 'flex', alignItems: 'flex-end', gap: 8, padding: '9px 11px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-md)' },
  textarea: { flex: 1, resize: 'none', border: 'none', outline: 'none', background: 'transparent', color: 'var(--text)', fontFamily: 'var(--font-ui)', fontSize: 15, lineHeight: 1.5, maxHeight: 150, padding: '6px 2px' },
  sendBtn: { width: 36, height: 36, flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 'var(--r-sm)', border: 'none', background: 'var(--primary)', color: '#16130F', cursor: 'pointer' },
  sendDisabled: { background: 'var(--surface-2)', color: 'var(--text-subtle)', cursor: 'not-allowed' },
  mentionPop: { position: 'absolute', bottom: 84, left: 20, right: 20, maxHeight: 220, overflowY: 'auto', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-lg)', padding: 6, zIndex: 20 },
  mentionItem: { display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '7px 8px', borderRadius: 'var(--r-sm)', border: 'none', background: 'transparent', cursor: 'pointer', textAlign: 'left', color: 'var(--text)' },

  roster: { width: 292, flexShrink: 0, background: 'var(--surface-2)', borderLeft: '1px solid var(--border)', padding: 14, display: 'flex', flexDirection: 'column', gap: 5, overflowY: 'auto' },
  rosterCard: { display: 'flex', alignItems: 'center', gap: 10, padding: '10px', borderRadius: 'var(--r-md)', border: '1px solid transparent', background: 'transparent', cursor: 'pointer', color: 'var(--text)' },
  assistiveTag: { padding: '0 6px', borderRadius: 'var(--r-pill)', background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-subtle)', fontWeight: 500 },

  empty: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, textAlign: 'center', padding: 28 },
  emptyIcon: { width: 56, height: 56, borderRadius: 'var(--r-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--primary-soft)', color: 'var(--primary)', fontSize: 26 },
  chips: { display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', maxWidth: 560 },
  chip: { display: 'inline-flex', alignItems: 'center', gap: 7, padding: '9px 13px', borderRadius: 'var(--r-md)', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 13, boxShadow: 'var(--shadow-sm)' },
  tenderHint: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 12px', borderRadius: 'var(--r-sm)', border: '1px dashed var(--border)', background: 'transparent', color: 'var(--text-subtle)', cursor: 'pointer', fontSize: 12.5 },

  scrim: { position: 'absolute', inset: 0, background: 'rgba(16,24,40,.45)', zIndex: 15 },
  scrimModal: { position: 'fixed', inset: 0, background: 'rgba(16,24,40,.45)', zIndex: 60, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 },
  modal: { width: '100%', maxWidth: 560, background: 'var(--surface)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-lg)', padding: 20, border: '1px solid var(--border)' },
  modalHead: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 },
  modalTa: { width: '100%', height: 220, resize: 'vertical', padding: 12, borderRadius: 'var(--r-sm)', border: '1px solid var(--border)', background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--font-ui)', fontSize: 14, lineHeight: 1.5, outline: 'none' },
  modalActions: { display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 },
  btnPrimary: { padding: '9px 16px', borderRadius: 'var(--r-sm)', border: 'none', background: 'var(--primary)', color: '#16130F', fontWeight: 600, cursor: 'pointer' },
  btnGhost: { padding: '9px 16px', borderRadius: 'var(--r-sm)', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', fontWeight: 600, cursor: 'pointer' },
}
