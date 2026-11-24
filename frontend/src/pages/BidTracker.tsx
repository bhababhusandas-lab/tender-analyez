import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  Trophy, FileText, Send, XCircle, MinusCircle, Trash2, Download,
  ChevronDown, TrendingUp, ArrowRight,
} from 'lucide-react'
import {
  fetchBids, fetchBidStats, updateBidStatus, deleteBid, downloadBidPdf,
  Bid, BidStats,
} from '../api/bids'
import { PageHeader, PageBody, StatTile, Section, EmptyState } from '../components/layout/PageHeader'

/* ═══════════════════════════════════════════════════════════════════════════
   BID TRACKER
   Every bid, past and present, as a register. Dense table over cards: an
   operator comparing eight tenders needs the deadlines in one column.
   ═══════════════════════════════════════════════════════════════════════════ */

const STATUSES = ['draft', 'submitted', 'won', 'lost', 'withdrawn'] as const

const STATUS_ICON: Record<string, React.ReactNode> = {
  draft:     <FileText className="w-3 h-3" />,
  submitted: <Send className="w-3 h-3" />,
  won:       <Trophy className="w-3 h-3" />,
  lost:      <XCircle className="w-3 h-3" />,
  withdrawn: <MinusCircle className="w-3 h-3" />,
}

const STATUS_CHIP: Record<string, string> = {
  draft: 'chip-idle', submitted: 'chip-info', won: 'chip-ok',
  lost: 'chip-risk', withdrawn: 'chip-warn',
}

function daysUntil(d: string | null | undefined): number | null {
  if (!d) return null
  const t = new Date(d).getTime()
  if (Number.isNaN(t)) return null
  return Math.ceil((t - Date.now()) / 86_400_000)
}

function Deadline({ raw }: { raw: string }) {
  const d = daysUntil(raw)
  if (d === null) return <span className="font-mono text-[11px] text-steel-400">—</span>
  const tone =
    d < 0 ? 'text-fg-subtle' :
    d <= 3 ? 'text-[#B42318] font-semibold' :
    d <= 7 ? 'text-amber-700 font-semibold' : 'text-fg-muted'
  return (
    <span className={`font-mono text-[11px] tnum ${tone}`}>
      {d < 0 ? `closed ${Math.abs(d)}d` : d === 0 ? 'today' : `${d}d left`}
    </span>
  )
}

function StatusMenu({ bid, onChange }: { bid: Bid; onChange: () => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const move = async (status: string) => {
    setBusy(true)
    try { await updateBidStatus(bid.id, status); onChange() } finally { setBusy(false); setOpen(false) }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        disabled={busy}
        className="inline-flex items-center gap-1 font-mono text-[10.5px] uppercase tracking-[0.1em]
                   text-fg-muted border border-edge rounded-chip px-2 py-1
                   hover:border-navy-900 hover:text-fg transition-colors disabled:opacity-50"
      >
        Move <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 z-20 min-w-[9rem] bg-panel border border-edge rounded-card shadow-raised py-1 animate-rise">
            {STATUSES.filter(s => s !== bid.status).map(s => (
              <button
                key={s}
                onClick={() => move(s)}
                className="w-full text-left text-[13px] px-3 py-1.5 capitalize flex items-center gap-2
                           text-fg-muted hover:bg-canvas hover:text-fg transition-colors"
              >
                {STATUS_ICON[s]} {s}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export function BidTracker() {
  const [bids, setBids] = useState<Bid[]>([])
  const [stats, setStats] = useState<BidStats | null>(null)
  const [filter, setFilter] = useState<string>('all')
  const [loading, setLoading] = useState(true)

  const [failed, setFailed] = useState(false)

  // Settled rather than all: a failing stats call must not leave the register
  // stuck on skeletons forever.
  const load = useCallback(async () => {
    setLoading(true)
    const [b, s] = await Promise.allSettled([
      fetchBids(filter === 'all' ? '' : filter),
      fetchBidStats(),
    ])
    if (b.status === 'fulfilled') { setBids(b.value); setFailed(false) }
    else { setBids([]); setFailed(true) }
    if (s.status === 'fulfilled') setStats(s.value)
    setLoading(false)
  }, [filter])

  useEffect(() => { load() }, [load])

  const remove = async (id: number) => {
    if (!confirm('Delete this bid? This cannot be undone.')) return
    await deleteBid(id)
    load()
  }

  const decided = (stats?.won ?? 0) + (stats?.lost ?? 0)
  const winRate = decided > 0 ? Math.round(((stats?.won ?? 0) / decided) * 100) : null

  return (
    <>
      <PageHeader
        eyebrow="Bid tracker"
        title="Every bid, past and present"
        subtitle="One register for what is drafted, submitted, won and lost."
        actions={
          <Link to="/app/bid" className="btn-primary btn-sm group">
            Run a tender
            <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
          </Link>
        }
      />

      <PageBody className="space-y-5">

        {/* ── Figures ── */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <StatTile label="Total bids" value={stats?.total ?? '—'} icon={<FileText className="w-4 h-4" />} />
          <StatTile label="Draft"      value={stats?.draft ?? '—'} icon={<FileText className="w-4 h-4" />} />
          <StatTile label="Submitted"  value={stats?.submitted ?? '—'} tone="live" icon={<Send className="w-4 h-4" />} />
          <StatTile label="Won"        value={stats?.won ?? '—'} tone="ok" icon={<Trophy className="w-4 h-4" />} />
          <StatTile
            label="Win rate"
            value={winRate === null ? '—' : `${winRate}%`}
            note={winRate === null ? 'No decided bids yet' : `${stats?.won} of ${decided} decided`}
            tone={winRate !== null && winRate >= 30 ? 'ok' : 'plain'}
            icon={<TrendingUp className="w-4 h-4" />}
          />
        </div>

        {/* ── Register ── */}
        <Section
          title="Register"
          meta={loading ? 'loading…' : `${bids.length} shown`}
          padded={false}
          action={
            <div className="flex gap-1 flex-wrap justify-end">
              {['all', ...STATUSES].map(f => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`font-mono text-[10px] uppercase tracking-[0.1em] px-2.5 py-1 rounded-chip border transition-colors
                    ${filter === f
                      ? 'bg-navy-900 text-white border-navy-900'
                      : 'bg-panel text-fg-muted border-edge hover:border-steel-400'}`}
                >
                  {f}
                </button>
              ))}
            </div>
          }
        >
          {loading ? (
            <div className="p-4 space-y-2">
              {[0, 1, 2, 3].map(i => <div key={i} className="skeleton h-12 rounded-card" />)}
            </div>
          ) : failed ? (
            <EmptyState
              icon={<XCircle className="w-5 h-5" />}
              title="Could not load your bids"
              body="The register did not come back from the server. Check your connection and try again — nothing has been lost."
              action={<button onClick={load} className="btn-ghost btn-sm">Retry</button>}
            />
          ) : bids.length === 0 ? (
            <EmptyState
              icon={<Trophy className="w-5 h-5" />}
              title={filter === 'all' ? 'No bids yet' : `Nothing marked ${filter}`}
              body="Run the bid pipeline on a live tender and save the result — it will appear here with its quote, confidence and deadline."
              action={<Link to="/app/bid" className="btn-primary btn-sm">Run a tender</Link>}
            />
          ) : (
            <div className="overflow-x-auto scrollbar-thin">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Tender</th>
                    <th className="hidden lg:table-cell">Portal</th>
                    <th>Status</th>
                    <th className="hidden md:table-cell text-right">Est. value</th>
                    <th className="text-right">Our quote</th>
                    <th className="text-right">Deadline</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {bids.map(bid => (
                    <tr key={bid.id}>
                      <td className="max-w-[24rem]">
                        <p className="font-medium text-fg truncate">{bid.tender_name || 'Untitled tender'}</p>
                        <p className="font-mono text-[10.5px] text-fg-subtle truncate">
                          {bid.reference_no || '—'}{bid.department ? ` · ${bid.department}` : ''}
                        </p>
                        {bid.notes && (
                          <p className="mt-1 text-[11.5px] text-fg-subtle line-clamp-1">{bid.notes}</p>
                        )}
                      </td>
                      <td className="hidden lg:table-cell">
                        <span className="font-mono text-[11px] text-fg-muted">{bid.portal || '—'}</span>
                      </td>
                      <td>
                        <span className={STATUS_CHIP[bid.status] || 'chip-info'}>
                          {STATUS_ICON[bid.status]} {bid.status}
                        </span>
                        {bid.bid_confidence && (
                          <p className="mt-1 font-mono text-[10px] text-fg-subtle">{bid.bid_confidence} confidence</p>
                        )}
                      </td>
                      <td className="hidden md:table-cell num text-fg-muted">
                        {bid.estimated_value ? `₹${bid.estimated_value}` : '—'}
                      </td>
                      <td className="num font-semibold">
                        {bid.recommended_quote ? `₹${bid.recommended_quote}` : '—'}
                      </td>
                      <td className="text-right"><Deadline raw={bid.submission_deadline} /></td>
                      <td>
                        <div className="flex items-center justify-end gap-1.5">
                          <StatusMenu bid={bid} onChange={load} />
                          <button
                            onClick={() =>
                              downloadBidPdf(
                                bid.id,
                                `Bid_${(bid.tender_name || 'tender').replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 50)}.pdf`,
                              ).catch(() => alert('Download failed.'))
                            }
                            aria-label="Download summary PDF"
                            title="Download summary PDF (1–2 pages)"
                            className="p-1.5 rounded-chip text-fg-subtle hover:text-fg hover:bg-sunk transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() =>
                              downloadBidPdf(
                                bid.id,
                                `Bid_${(bid.tender_name || 'tender').replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 50)}_Full.pdf`,
                                true,
                              ).catch(() => alert('Download failed.'))
                            }
                            aria-label="Download full report PDF"
                            title="Download full report (summary + every specialist's report)"
                            className="p-1.5 rounded-chip text-fg-subtle hover:text-fg hover:bg-sunk transition-colors"
                          >
                            <FileText className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => remove(bid.id)}
                            aria-label="Delete bid"
                            title="Delete bid"
                            className="p-1.5 rounded-chip text-steel-400 hover:text-[#B42318] hover:bg-red-50 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </PageBody>
    </>
  )
}
