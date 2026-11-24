import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, ListChecks, Trophy, FileWarning, Zap, AlertTriangle,
  Check, Loader2, ShieldCheck, IndianRupee, PlayCircle, FolderLock, TrendingUp,
} from 'lucide-react'
import { PageHeader, PageBody, StatTile, Section, EmptyState } from '../components/layout/PageHeader'
import { fetchBids, fetchBidStats, type Bid, type BidStats } from '../api/bids'
import { fetchStats as fetchVaultStats, type VaultStats } from '../api/documents'
import { fetchUsage, type UsageSnapshot } from '../api/usage'
import { useAuth } from '../auth/AuthContext'

/* ═══════════════════════════════════════════════════════════════════════════
   COMMAND CENTRE
   ───────────────────────────────────────────────────────────────────────────
   The screen the operator lands on. It answers four questions in one glance:
     What is closing soon?   What is at risk?   What did the team find?
     What should I do next?
   Everything here is live data. Where a figure does not exist yet the tile
   says so rather than showing a zero that reads as a real measurement.
   ═══════════════════════════════════════════════════════════════════════════ */

/** Days until a date string; null if unparseable. */
function daysUntil(d: string | null | undefined): number | null {
  if (!d) return null
  const t = new Date(d).getTime()
  if (Number.isNaN(t)) return null
  return Math.ceil((t - Date.now()) / 86_400_000)
}

function DeadlinePill({ days }: { days: number | null }) {
  if (days === null) return <span className="font-mono text-[10.5px] text-steel-400">No deadline</span>
  if (days < 0)   return <span className="chip-risk">Closed {Math.abs(days)}d ago</span>
  if (days === 0) return <span className="chip-risk">Closes today</span>
  if (days <= 3)  return <span className="chip-risk">{days}d left</span>
  if (days <= 7)  return <span className="chip-warn">{days}d left</span>
  return <span className="chip-info">{days}d left</span>
}

const STATUS_CHIP: Record<string, string> = {
  draft: 'chip-idle', submitted: 'chip-info', won: 'chip-ok',
  lost: 'chip-risk', withdrawn: 'chip-warn',
}

/* ── The eleven, as a live activity board ────────────────────────────────── */

const AGENT_BOARD = [
  { name: 'Bid Manager',         module: 'Eligibility scoring' },
  { name: 'Market Intelligence', module: 'Competitor research' },
  { name: 'Legal & Compliance',  module: 'Clause risk review' },
  { name: 'Govt Relations',      module: 'Pre-bid queries' },
  { name: 'Technical Expert',    module: 'Compliance matrix' },
  { name: 'Technical Writer',    module: 'Proposal drafting' },
  { name: 'Finance & Accounts',  module: 'BOQ & GST' },
  { name: 'Bid Pricing',         module: 'L1 price band' },
  { name: 'Document Controller', module: 'Certificate audit' },
  { name: 'Admin & HR',          module: 'Key personnel' },
  { name: 'QA Reviewer',         module: 'Final gate' },
]

function AgentBoard({ running }: { running: boolean }) {
  // With no run in flight the board shows the roster at rest. During a run the
  // caller drives `running`, and the strip animates through the eleven.
  const [cursor, setCursor] = useState(0)

  useEffect(() => {
    if (!running) { setCursor(0); return }
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) { setCursor(AGENT_BOARD.length); return }
    const id = setInterval(() => setCursor(c => (c + 1) % (AGENT_BOARD.length + 1)), 900)
    return () => clearInterval(id)
  }, [running])

  return (
    <ul className="divide-y divide-edge">
      {AGENT_BOARD.map((a, i) => {
        const state = !running ? 'idle' : i < cursor ? 'done' : i === cursor ? 'run' : 'wait'
        return (
          <li
            key={a.name}
            className={`flex items-center gap-3 px-4 py-2.5 transition-colors duration-300
              ${state === 'run' ? 'bg-saffron-50' : ''}`}
          >
            <span className="w-4 flex-none grid place-items-center">
              {state === 'done' && <Check className="w-3.5 h-3.5 text-sage-500" strokeWidth={3} />}
              {state === 'run'  && <Loader2 className="w-3.5 h-3.5 text-accent animate-spin" />}
              {(state === 'wait' || state === 'idle') && (
                <span className={`w-1.5 h-1.5 rounded-full ${state === 'idle' ? 'bg-steel-300' : 'bg-steel-200'}`} />
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-medium text-fg leading-tight truncate">{a.name}</span>
              <span className="block font-mono text-[10px] text-fg-subtle truncate">{a.module}</span>
            </span>
            <span className={`font-mono text-[10px] uppercase tracking-[0.1em] flex-none
              ${state === 'run' ? 'text-accent' : state === 'done' ? 'text-sage-600' : 'text-steel-400'}`}>
              {state === 'done' ? 'cleared' : state === 'run' ? 'running' : state === 'idle' ? 'ready' : 'queued'}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/* ── Page ────────────────────────────────────────────────────────────────── */

export function Overview() {
  const { user } = useAuth()
  const [bids, setBids] = useState<Bid[]>([])
  const [stats, setStats] = useState<BidStats | null>(null)
  const [vault, setVault] = useState<VaultStats | null>(null)
  const [usage, setUsage] = useState<UsageSnapshot | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    Promise.allSettled([fetchBids(), fetchBidStats(), fetchVaultStats(), fetchUsage()])
      .then(([b, s, v, u]) => {
        if (!alive) return
        if (b.status === 'fulfilled') setBids(b.value)
        if (s.status === 'fulfilled') setStats(s.value)
        if (v.status === 'fulfilled') setVault(v.value)
        if (u.status === 'fulfilled') setUsage(u.value)
        setLoading(false)
      })
    return () => { alive = false }
  }, [])

  const firstName = (user?.full_name || '').trim().split(' ')[0]

  // Win rate is only meaningful once something has been decided.
  const decided = (stats?.won ?? 0) + (stats?.lost ?? 0)
  const winRate = decided > 0 ? Math.round(((stats?.won ?? 0) / decided) * 100) : null

  const open = bids
    .filter(b => b.status === 'draft' || b.status === 'submitted')
    .map(b => ({ b, d: daysUntil(b.submission_deadline) }))
    .sort((x, y) => (x.d ?? 9e9) - (y.d ?? 9e9))

  const closingSoon = open.filter(o => o.d !== null && o.d >= 0 && o.d <= 7).length
  const runsLeft = usage?.limits.monthly != null
    ? Math.max(0, usage.limits.monthly - usage.used_30d)
    : null

  return (
    <>
      <PageHeader
        eyebrow="Command centre"
        title={firstName ? `Good to see you, ${firstName}.` : 'Command centre'}
        subtitle="Everything closing, everything at risk, and what the team found — on one screen."
        actions={
          <>
            <Link to="/app/bids" className="btn-ghost btn-sm">Bid tracker</Link>
            <Link to="/app/bid" className="btn-primary btn-sm group">
              Run a tender
              <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </>
        }
      />

      <PageBody className="space-y-5">

        {/* ══ Figures ══ */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile
            label="Open bids"
            value={loading ? '—' : open.length}
            note={closingSoon > 0 ? `${closingSoon} closing within 7 days` : 'Draft and submitted'}
            tone={closingSoon > 0 ? 'warn' : 'plain'}
            icon={<ListChecks className="w-4 h-4" />}
          />
          <StatTile
            label="Win rate"
            value={winRate === null ? '—' : `${winRate}%`}
            note={winRate === null ? 'No decided bids yet' : `${stats?.won} won of ${decided} decided`}
            tone={winRate !== null && winRate >= 30 ? 'ok' : 'plain'}
            icon={<Trophy className="w-4 h-4" />}
          />
          <StatTile
            label="Documents at risk"
            value={loading ? '—' : (vault ? vault.expired + vault.expiring_soon : 0)}
            note={vault ? `${vault.expired} expired · ${vault.expiring_soon} expiring` : 'Vault not loaded'}
            tone={vault && vault.expired > 0 ? 'risk' : vault && vault.expiring_soon > 0 ? 'warn' : 'ok'}
            icon={<FileWarning className="w-4 h-4" />}
          />
          <StatTile
            label="Pipeline runs left"
            value={runsLeft === null ? '∞' : runsLeft}
            note={usage ? `${usage.plan} plan · ${usage.used_30d} used in 30d` : 'Loading plan'}
            tone={runsLeft !== null && runsLeft <= 2 ? 'warn' : 'live'}
            icon={<Zap className="w-4 h-4" />}
          />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">

          {/* ══ Pipeline ══ */}
          <div className="xl:col-span-2 space-y-5">
            <Section
              title="Bid pipeline"
              meta={`${open.length} open`}
              padded={false}
              action={<Link to="/app/bids" className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-accent hover:text-saffron-700">View all</Link>}
            >
              {loading ? (
                <div className="p-4 space-y-2">
                  {[0, 1, 2].map(i => <div key={i} className="skeleton h-12 rounded-card" />)}
                </div>
              ) : open.length === 0 ? (
                <EmptyState
                  icon={<PlayCircle className="w-5 h-5" />}
                  title="No open bids"
                  body="Run a live tender through the eleven specialists and it will appear here with its deadline, quote and open risks."
                  action={<Link to="/app/bid" className="btn-primary btn-sm">Run a tender</Link>}
                />
              ) : (
                <div className="overflow-x-auto scrollbar-thin">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Tender</th>
                        <th className="hidden md:table-cell">Portal</th>
                        <th>Status</th>
                        <th className="text-right">Our quote</th>
                        <th className="text-right">Deadline</th>
                      </tr>
                    </thead>
                    <tbody>
                      {open.slice(0, 8).map(({ b, d }) => (
                        <tr key={b.id} className="group">
                          <td className="max-w-[22rem]">
                            <p className="font-medium text-fg truncate">{b.tender_name || 'Untitled tender'}</p>
                            <p className="font-mono text-[10.5px] text-fg-subtle truncate">
                              {b.reference_no || '—'}{b.department ? ` · ${b.department}` : ''}
                            </p>
                          </td>
                          <td className="hidden md:table-cell">
                            <span className="font-mono text-[11px] text-fg-muted">{b.portal || '—'}</span>
                          </td>
                          <td>
                            <span className={STATUS_CHIP[b.status] || 'chip-info'}>{b.status}</span>
                          </td>
                          <td className="num">{b.recommended_quote ? `₹${b.recommended_quote}` : '—'}</td>
                          <td className="text-right"><DeadlinePill days={d} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>

            {/* ══ What the team found ══ */}
            <Section title="Compliance status" meta="Latest run">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <ComplianceTile
                  icon={<ShieldCheck className="w-4 h-4" />}
                  label="Eligibility"
                  value={stats && stats.total > 0 ? 'Checked' : 'Not run yet'}
                  detail={stats && stats.total > 0
                    ? 'Turnover, experience and registration thresholds tested against your profile.'
                    : 'Run a tender to test your profile against its eligibility clauses.'}
                  tone={stats && stats.total > 0 ? 'ok' : 'idle'}
                />
                <ComplianceTile
                  icon={<AlertTriangle className="w-4 h-4" />}
                  label="Certificates"
                  value={vault ? (vault.expired > 0 ? `${vault.expired} expired` : vault.expiring_soon > 0 ? `${vault.expiring_soon} expiring` : 'All valid') : '—'}
                  detail={vault && (vault.expired > 0 || vault.expiring_soon > 0)
                    ? 'A lapsed certificate disqualifies a bid before price is opened. Renew before you submit.'
                    : 'Every document in the vault is inside its validity window.'}
                  tone={vault && vault.expired > 0 ? 'risk' : vault && vault.expiring_soon > 0 ? 'warn' : 'ok'}
                  href="/app/vault"
                />
                <ComplianceTile
                  icon={<IndianRupee className="w-4 h-4" />}
                  label="BOQ & pricing"
                  value={stats && stats.total > 0 ? 'Costed' : 'Not run yet'}
                  detail={stats && stats.total > 0
                    ? 'Line items costed with GST treatment and a defended price band.'
                    : 'BOQ lines and the L1 price band are produced by the pipeline run.'}
                  tone={stats && stats.total > 0 ? 'ok' : 'idle'}
                />
              </div>
            </Section>
          </div>

          {/* ══ Right rail ══ */}
          <div className="space-y-5">
            <Section
              title="The AI team"
              meta="11 specialists"
              padded={false}
              action={<Link to="/app/dashboard" className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-accent hover:text-saffron-700">Open</Link>}
            >
              <AgentBoard running={false} />
              <div className="px-4 py-3 border-t border-edge bg-canvas">
                <Link to="/app/bid" className="btn-primary btn-sm w-full group">
                  Put a tender through the team
                  <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
                </Link>
              </div>
            </Section>

            <Section title="Document vault" meta={vault ? `${vault.total} files` : ''} padded={false}>
              {loading ? (
                <div className="p-4 space-y-2">
                  {[0, 1, 2].map(i => <div key={i} className="skeleton h-8 rounded-card" />)}
                </div>
              ) : vault ? (
                <div className="divide-y divide-edge">
                  <VaultRow label="Valid"        value={vault.valid}         tone="ok" />
                  <VaultRow label="Expiring soon" value={vault.expiring_soon} tone="warn" />
                  <VaultRow label="Expired"       value={vault.expired}       tone="risk" />
                  <div className="px-4 py-3">
                    <Link to="/app/vault" className="btn-ghost btn-sm w-full">
                      <FolderLock className="w-3.5 h-3.5" /> Open vault
                    </Link>
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon={<FolderLock className="w-5 h-5" />}
                  title="Vault empty"
                  body="Upload your ISO certificates, GST returns, ITRs and registrations once. Every run then checks them against the tender schedule."
                  action={<Link to="/app/vault" className="btn-ghost btn-sm">Open vault</Link>}
                />
              )}
            </Section>

            <Section title="Results" meta="All time">
              <dl className="grid grid-cols-3 gap-3 text-center">
                <ResultFig label="Won"  value={stats?.won ?? 0}  tone="ok" />
                <ResultFig label="Lost" value={stats?.lost ?? 0} tone="risk" />
                <ResultFig label="Live" value={stats?.submitted ?? 0} tone="live" />
              </dl>
              {winRate !== null && (
                <div className="mt-4">
                  <div className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-[0.12em] text-fg-subtle">
                    <span>Win rate</span>
                    <span className="tnum text-sage-600 inline-flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" />{winRate}%
                    </span>
                  </div>
                  <div className="mt-1.5 h-1.5 bg-sunk rounded-full overflow-hidden">
                    <div
                      className="h-full bg-sage-500 origin-left animate-bar-fill"
                      style={{ width: `${winRate}%` }}
                    />
                  </div>
                </div>
              )}
            </Section>
          </div>
        </div>
      </PageBody>
    </>
  )
}

/* ── Bits ────────────────────────────────────────────────────────────────── */

function ComplianceTile({
  icon, label, value, detail, tone, href,
}: {
  icon: React.ReactNode; label: string; value: string; detail: string
  tone: 'ok' | 'warn' | 'risk' | 'idle'; href?: string
}) {
  const ring = {
    ok:   'border-sage-300 bg-sage-50 text-sage-700',
    warn: 'border-amber-300 bg-amber-50 text-amber-700',
    risk: 'border-red-200 bg-red-50 text-[#B42318]',
    idle: 'border-edge bg-canvas text-fg-subtle',
  }[tone]

  const inner = (
    <div className="h-full rounded-card border border-edge bg-panel p-4 lift hover:border-edge-strong hover:shadow-card">
      <div className="flex items-center gap-2">
        <span className={`grid place-items-center w-7 h-7 rounded-chip border ${ring}`}>{icon}</span>
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-subtle">{label}</p>
      </div>
      <p className="mt-2.5 font-display text-[15px] font-bold text-fg">{value}</p>
      <p className="mt-1 text-[12px] text-fg-subtle leading-relaxed">{detail}</p>
    </div>
  )

  return href ? <Link to={href} className="block h-full">{inner}</Link> : inner
}

function VaultRow({ label, value, tone }: { label: string; value: number; tone: 'ok' | 'warn' | 'risk' }) {
  const dot = { ok: 'bg-sage-500', warn: 'bg-amber-500', risk: 'bg-[#B42318]' }[tone]
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <span className={`w-1.5 h-1.5 rounded-full flex-none ${dot}`} />
      <span className="text-[13px] text-fg-muted flex-1">{label}</span>
      <span className="font-mono text-[13px] font-semibold text-fg tnum">{value}</span>
    </div>
  )
}

function ResultFig({ label, value, tone }: { label: string; value: number; tone: 'ok' | 'risk' | 'live' }) {
  const c = { ok: 'text-sage-600', risk: 'text-[#B42318]', live: 'text-accent' }[tone]
  return (
    <div>
      <dd className={`font-display text-2xl font-bold tnum ${c}`}>{value}</dd>
      <dt className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-fg-subtle">{label}</dt>
    </div>
  )
}
