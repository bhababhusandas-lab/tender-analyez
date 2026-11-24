import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Check, ShieldCheck } from 'lucide-react'
import { Logo } from '../brand/Logo'

/**
 * Shared frame for sign-in, sign-up and verification.
 *
 * Navy proof panel on the left, white form on the right. All three auth screens
 * use it, so the brand ground never flips between steps in the same flow — a
 * shifting background mid-signup is the cheapest way to look untrustworthy.
 */
export function AuthShell({
  eyebrow, title, accent, blurb, bullets, children,
}: {
  eyebrow: string
  title: string
  accent: string
  blurb: string
  bullets: string[]
  children: ReactNode
}) {
  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-panel">

      {/* ── Proof panel ── */}
      <aside className="on-dark hidden lg:flex relative bg-navy-900 overflow-hidden flex-col justify-between p-12">
        <div className="absolute inset-0 bg-grid-dark opacity-70 layer" />
        <div className="absolute inset-0 bloom-brand opacity-80 layer" />

        <div className="relative"><Logo size={38} /></div>

        <div className="relative">
          <div className="flex items-center gap-3">
            <span className="w-6 h-px bg-saffron-500" />
            <p className="eyebrow text-saffron-500">{eyebrow}</p>
          </div>
          <h1 className="mt-5 text-display-lg text-white text-balance">
            {title} <span className="text-saffron-500">{accent}</span>
          </h1>
          <p className="mt-5 text-steel-300 max-w-md leading-relaxed">{blurb}</p>

          <ul className="mt-9 space-y-3 max-w-md">
            {bullets.map(b => (
              <li key={b} className="flex items-start gap-2.5 text-sm text-steel-300">
                <Check className="w-4 h-4 mt-0.5 flex-none text-sage-300" strokeWidth={3} />
                {b}
              </li>
            ))}
          </ul>
        </div>

        <div className="relative flex items-center gap-2 font-mono text-[10px] tracking-[0.14em] text-fg-subtle">
          <ShieldCheck className="w-3.5 h-3.5 text-sage-300" />
          TLS 1.3 · ENCRYPTED AT REST · ACCOUNT-ISOLATED
        </div>
      </aside>

      {/* ── Form ── */}
      <main className="flex flex-col">
        <div className="on-dark lg:hidden px-5 h-[68px] flex items-center bg-navy-900">
          <Logo size={34} />
        </div>
        <div className="flex-1 flex items-center justify-center px-5 sm:px-8 py-12 sm:py-16">
          <div className="w-full max-w-md">{children}</div>
        </div>
      </main>
    </div>
  )
}

/** Form heading used above each auth card. */
export function AuthHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub: string }) {
  return (
    <div className="mb-6">
      <p className="eyebrow text-accent">{eyebrow}</p>
      <h2 className="mt-3 text-display-md text-fg">{title}</h2>
      <p className="mt-2 text-sm text-fg-muted">{sub}</p>
    </div>
  )
}

/** Labelled input with a leading icon. */
export function AuthField({
  label, icon, ...input
}: { label: string; icon: ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label htmlFor={input.id} className="block font-mono text-[10px] uppercase tracking-[0.14em] text-fg-subtle mb-1.5">
        {label}
      </label>
      <div className="relative">
        <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-steel-400 pointer-events-none">
          {icon}
        </span>
        <input
          {...input}
          className="w-full pl-10 pr-3.5 py-2.5 text-sm bg-panel border border-edge-strong rounded-card
                     text-fg placeholder-steel-400 outline-none transition-colors
                     focus:border-saffron-500"
        />
      </div>
    </div>
  )
}

/** Footer links under an auth card. */
export function AuthFooter({ prompt, linkTo, linkLabel }: { prompt: string; linkTo: string; linkLabel: string }) {
  return (
    <>
      <p className="mt-6 text-sm text-fg-muted text-center">
        {prompt}{' '}
        <Link to={linkTo} className="font-semibold text-accent hover:text-saffron-700 transition-colors">
          {linkLabel}
        </Link>
      </p>
      <p className="mt-3 text-center">
        <Link to="/" className="font-mono text-[11px] text-fg-subtle hover:text-fg transition-colors">
          ← Back to home
        </Link>
      </p>
    </>
  )
}
