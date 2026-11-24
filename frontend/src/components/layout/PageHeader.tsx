import { ReactNode } from 'react'
import { DeadlineBell, useDeadlines } from './DeadlineBell'

/**
 * Every workspace screen opens the same way: a mono eyebrow naming the module,
 * the screen title, one line of orientation, and the screen's actions on the
 * right. Consistency here is what makes a dense product feel navigable — the
 * operator's eye lands in the same place on every page.
 */
export function PageHeader({
  eyebrow, title, subtitle, actions,
}: {
  eyebrow: string
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  const deadlines = useDeadlines()
  return (
    <header className="border-b border-edge bg-panel">
      <div className="px-5 sm:px-7 py-5 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">{eyebrow}</p>
          <h1 className="mt-1.5 font-display text-[26px] font-bold text-fg leading-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-fg-muted">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2 flex-none">
          <div className="hidden lg:block"><DeadlineBell state={deadlines} align="right" light /></div>
          {actions}
        </div>
      </div>
    </header>
  )
}

/** Standard content well. Keeps every screen on the same gutters and measure. */
export function PageBody({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`px-5 sm:px-7 py-6 ${className}`}>{children}</div>
}

/**
 * Stat tile. Figure first and large, label under it in mono — the reverse of
 * the usual SaaS card, because on this screen the number is what is being read.
 */
export function StatTile({
  label, value, note, tone = 'plain', icon,
}: {
  label: string
  value: ReactNode
  note?: string
  tone?: 'plain' | 'ok' | 'warn' | 'risk' | 'live'
  icon?: ReactNode
}) {
  const accent = {
    plain: 'text-fg',
    ok:    'text-sage-600',
    warn:  'text-amber-700',
    risk:  'text-[#B42318]',
    live:  'text-accent',
  }[tone]

  const bar = {
    plain: 'bg-steel-300',
    ok:    'bg-sage-500',
    warn:  'bg-amber-500',
    risk:  'bg-[#B42318]',
    live:  'bg-saffron-500',
  }[tone]

  return (
    <div className="relative bg-panel border border-edge rounded-panel p-4 overflow-hidden">
      <span className={`absolute left-0 top-0 bottom-0 w-[3px] ${bar}`} />
      <div className="flex items-start justify-between gap-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-subtle">{label}</p>
        {icon && <span className="text-fg-subtle flex-none">{icon}</span>}
      </div>
      <p className={`mt-2 font-display text-[28px] font-bold leading-none tnum ${accent}`}>{value}</p>
      {note && <p className="mt-1.5 text-[11px] text-fg-subtle leading-snug">{note}</p>}
    </div>
  )
}

/** Section panel with a titled head — the unit every dense screen is built from. */
export function Section({
  title, meta, action, children, padded = true,
}: {
  title: string
  meta?: string
  action?: ReactNode
  children: ReactNode
  padded?: boolean
}) {
  return (
    <section className="bg-panel border border-edge rounded-panel overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-edge bg-canvas">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <h2 className="font-display text-[14px] font-bold text-fg truncate">{title}</h2>
          {meta && <span className="font-mono text-[10.5px] text-fg-subtle flex-none">{meta}</span>}
        </div>
        {action && <div className="flex-none">{action}</div>}
      </div>
      <div className={padded ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

/** Empty state. Never a shrug — always names the next action. */
export function EmptyState({
  icon, title, body, action,
}: { icon: ReactNode; title: string; body: string; action?: ReactNode }) {
  return (
    <div className="text-center py-14 px-6">
      <span className="inline-grid place-items-center w-12 h-12 rounded-card bg-sunk text-fg-subtle">
        {icon}
      </span>
      <h3 className="mt-4 font-display text-[15px] font-bold text-fg">{title}</h3>
      <p className="mt-1.5 text-sm text-fg-subtle max-w-sm mx-auto leading-relaxed">{body}</p>
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  )
}
