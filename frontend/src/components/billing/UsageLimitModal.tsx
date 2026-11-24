import { X, Sparkles, Check, ArrowRight, Mail, Clock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { UsageLimitInfo } from '../../api/usage'

interface Props {
  info: UsageLimitInfo
  onClose: () => void
}

const PLANS = [
  {
    id: 'starter',
    name: 'Starter',
    price: '₹9,999',
    period: '/ mo',
    blurb: '10 bid pipelines / month · 1 lifecycle analysis',
    features: ['All 11 AI agents', '7-phase Analysis (1/mo)', 'Document Vault (50 docs)', 'Email support'],
    cta: 'Upgrade to Starter',
    highlighted: false,
  },
  {
    id: 'growth',
    name: 'Growth',
    price: '₹24,999',
    period: '/ mo',
    blurb: '25 bid pipelines / month · 3 lifecycle analyses',
    features: ['All 11 AI specialists', '7-phase Analysis (3/mo)', 'Document Vault (70 docs)', 'Bid Tracker', 'Email support'],
    cta: 'Upgrade to Growth',
    highlighted: false,
  },
  {
    id: 'professional',
    name: 'Professional',
    price: '₹49,999',
    period: '/ mo',
    blurb: 'Unlimited bid pipelines and lifecycle analyses',
    features: ['Unlimited bid pipelines', 'Unlimited 7-phase Analysis', 'Priority queue', 'Priority support'],
    cta: 'Upgrade to Professional',
    highlighted: true,
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    blurb: 'Unlimited · team seats · SSO',
    features: ['Unlimited everything', 'Team seats (5+)', 'Dedicated account manager', 'Custom integrations'],
    cta: 'Contact sales',
    highlighted: false,
    isEnterprise: true,
  },
]

const HEADLINES: Record<UsageLimitInfo['limit_type'], string> = {
  total:   "You've reached your plan limit.",
  daily:   "You've hit your daily limit.",
  monthly: "You've hit your monthly limit.",
}

const SUBHEADLINES: Record<UsageLimitInfo['limit_type'], string> = {
  total:   "Upgrade to keep running tenders — pick the plan that fits your bid volume.",
  daily:   "The 24-hour window will reset shortly. Or upgrade now for more headroom.",
  monthly: "Wait for the rolling 30-day window to free up — or upgrade for more capacity.",
}

export function UsageLimitModal({ info, onClose }: Props) {
  const headline = HEADLINES[info.limit_type] ?? "You've reached your plan limit."
  const sub = SUBHEADLINES[info.limit_type] ?? "Upgrade to continue using the platform."
  const isFree = info.plan === 'free' || info.plan === 'trial'

  // Only show the current user's next available plan tiers.
  const recommendedPlans = isFree
    ? PLANS
    : info.plan === 'starter'
      ? PLANS.filter(p => p.id !== 'starter')
      : info.plan === 'growth'
        ? PLANS.filter(p => p.id === 'professional' || p.id === 'enterprise')
      : info.plan === 'professional'
        ? PLANS.filter(p => p.id === 'enterprise')
        : PLANS

  const resetText = info.resets_at
    ? `Window resets at ${new Date(info.resets_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}`
    : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-ink-900/70 backdrop-blur-sm overflow-y-auto" onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        className="relative bg-cream-50 w-full max-w-5xl rounded-3xl shadow-2xl overflow-hidden border border-ink-200 my-auto"
      >
        <button onClick={onClose} aria-label="Close"
          className="absolute top-4 right-4 z-10 p-2 rounded-full bg-panel hover:bg-ink-100 border border-ink-200 transition">
          <X className="w-4 h-4 text-ink-700" />
        </button>

        {/* Header */}
        <div className="bg-ink-paper text-cream-100 px-8 py-10 sm:px-12 sm:py-12 relative overflow-hidden">
          <div className="absolute inset-0 bg-dotgrid-light pointer-events-none opacity-50" />
          <div className="absolute -top-32 -right-32 w-[400px] h-[400px] bg-ink-700/30 rounded-full blur-3xl pointer-events-none" />
          <div className="relative">
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-cream-100/10 border border-cream-100/20 text-[11px] font-semibold text-cream-200 font-mono tracking-widest">
              <Sparkles className="w-3.5 h-3.5" /> {info.limit_type.toUpperCase()} LIMIT
            </span>
            <h2 className="mt-5 font-display text-3xl sm:text-5xl leading-[1.05]">{headline}</h2>
            <p className="mt-4 text-cream-100/80 max-w-2xl">{sub}</p>
            <div className="mt-5 flex flex-wrap items-center gap-5 text-sm">
              <div className="flex items-center gap-2 text-cream-100/80">
                <span className="font-mono text-xs tracking-widest text-cream-200">YOUR PLAN</span>
                <span className="px-2.5 py-1 rounded-full bg-cream-100/10 border border-cream-100/20 capitalize font-medium">{info.plan}</span>
              </div>
              <div className="flex items-center gap-2 text-cream-100/80">
                <span className="font-mono text-xs tracking-widest text-cream-200">USED</span>
                <span className="font-display text-xl">{info.used} <span className="text-cream-100/40 text-sm">/ {info.limit}</span></span>
              </div>
              {resetText && (
                <div className="flex items-center gap-1.5 text-cream-100/60">
                  <Clock className="w-3.5 h-3.5" /><span className="text-xs">{resetText}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Plans */}
        <div className="p-6 sm:p-10">
          <p className="eyebrow text-ink-900 text-center">Pick what fits</p>
          <h3 className="mt-2 font-display text-2xl sm:text-3xl text-ink-900 text-center">Upgrade in 30 seconds.</h3>

          <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
            {recommendedPlans.map(p => (
              <div key={p.id}
                className={`rounded-2xl p-6 flex flex-col card-hover h-full relative overflow-hidden ${
                  p.highlighted
                    ? 'bg-ink-paper text-cream-100 border border-ink-700'
                    : 'bg-panel border border-ink-200'
                }`}>
                {p.highlighted && (
                  <>
                    <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-ink-600 via-ink-400 to-ink-600" />
                    <div className="absolute top-3 right-3 px-2 py-0.5 bg-cream-100 text-ink-900 text-[9px] font-bold font-mono rounded-full uppercase tracking-wider">Recommended</div>
                  </>
                )}
                <p className={`eyebrow ${p.highlighted ? 'text-cream-200' : 'text-ink-900'}`}>{p.name}</p>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className={`font-display text-4xl ${p.highlighted ? 'text-cream-100' : 'text-ink-900'} leading-none`}>{p.price}</span>
                  <span className={`text-xs ml-1 ${p.highlighted ? 'text-cream-100/60' : 'text-ink-500'}`}>{p.period}</span>
                </div>
                <p className={`mt-2 text-xs font-mono ${p.highlighted ? 'text-cream-200' : 'text-ink-700'}`}>{p.blurb}</p>
                <ul className="mt-4 space-y-2 flex-1 text-sm">
                  {p.features.map(f => (
                    <li key={f} className={`flex items-start gap-2 ${p.highlighted ? 'text-cream-100/90' : 'text-ink-700'}`}>
                      <span className={`w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${p.highlighted ? 'bg-cream-100/15 text-cream-100' : 'bg-cream-200 text-ink-900'}`}>
                        <Check className="w-2.5 h-2.5" />
                      </span>
                      {f}
                    </li>
                  ))}
                </ul>
                {p.isEnterprise ? (
                  <a href="mailto:admin@example.com?subject=Enterprise%20Plan%20Enquiry"
                    className="mt-5 block text-center py-2.5 rounded-full font-semibold text-sm bg-ink-900 hover:bg-ink-700 text-white transition flex items-center justify-center gap-1.5">
                    <Mail className="w-3.5 h-3.5" /> {p.cta}
                  </a>
                ) : (
                  <Link to="/app/overview"
                    className={`mt-5 block text-center py-2.5 rounded-full font-semibold text-sm transition flex items-center justify-center gap-1.5 ${
                      p.highlighted
                        ? 'bg-cream-100 text-ink-900 hover:bg-panel'
                        : 'bg-ink-900 hover:bg-ink-700 text-white'
                    }`}>
                    {p.cta} <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                )}
              </div>
            ))}
          </div>

          <p className="mt-6 text-xs text-ink-500 text-center">
            Questions about plans? Email <a href="mailto:admin@example.com" className="text-ink-900 font-semibold link-grow">admin@example.com</a> — we usually reply within a working day.
          </p>
        </div>
      </div>
    </div>
  )
}
