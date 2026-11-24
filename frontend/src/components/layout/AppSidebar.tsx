import { useState } from 'react'
import { NavLink, useNavigate, Link } from 'react-router-dom'
import {
  Gauge, PlayCircle, GitBranch, ListChecks, FolderLock,
  Building2, Users, Shield, LogOut, Menu, X, ArrowRight, type LucideIcon,
} from 'lucide-react'
import { Logo } from '../brand/Logo'
import { useAuth } from '../../auth/AuthContext'
import { ThemeToggle } from '../../theme/ThemeToggle'
import { SidebarHistory } from '../history/SidebarHistory'
import { DeadlineBell, DeadlinePopup, useDeadlines } from './DeadlineBell'

type Item = { to: string; label: string; icon: LucideIcon; end?: boolean }

/**
 * Grouped by what the operator is doing, not by how the app is built.
 * "Run a bid" is the money path, so it sits directly under the command centre
 * and nothing decorative is allowed above it.
 */
const GROUPS: { heading: string; items: Item[] }[] = [
  {
    heading: 'Command',
    items: [{ to: '/app/overview', label: 'Command Centre', icon: Gauge }],
  },
  {
    heading: 'Bid',
    items: [
      { to: '/app/bid',      label: 'Bid Pipeline',     icon: PlayCircle },
      { to: '/app/analysis', label: '7-Phase Analysis', icon: GitBranch },
      { to: '/app/bids',     label: 'Bid Tracker',      icon: ListChecks },
    ],
  },
  {
    heading: 'Company',
    items: [
      { to: '/app/vault',   label: 'Document Vault',  icon: FolderLock },
      { to: '/app/profile', label: 'Company Profile', icon: Building2 },
    ],
  },
  {
    heading: 'Team',
    items: [{ to: '/app/dashboard', label: 'The AI Team', icon: Users }],
  },
]

const ADMIN: Item = { to: '/app/admin/users', label: 'Admin', icon: Shield }

function NavItem({ item, onNavigate }: { item: Item; onNavigate?: () => void }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      onClick={onNavigate}
      className={({ isActive }) =>
        `group relative flex items-center gap-3 pl-4 pr-3 py-2 text-[13.5px] font-medium transition-colors
         ${isActive
           ? 'bg-navy-800 text-white'
           : 'text-steel-400 hover:text-white hover:bg-navy-800/60'}`
      }
    >
      {({ isActive }) => (
        <>
          {/* Active state is a saffron edge marker, not a filled pill — it reads
              as a tab in a filing rail. */}
          <span
            className={`absolute left-0 top-0 bottom-0 w-[3px] transition-colors
              ${isActive ? 'bg-saffron-500' : 'bg-transparent'}`}
          />
          <Icon
            className={`w-[17px] h-[17px] flex-none transition-colors
              ${isActive ? 'text-saffron-500' : 'text-fg-subtle group-hover:text-steel-300'}`}
            strokeWidth={2}
          />
          <span className="truncate">{item.label}</span>
        </>
      )}
    </NavLink>
  )
}

export function AppSidebar() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const deadlines = useDeadlines()

  const groups = user?.is_admin
    ? [...GROUPS, { heading: 'Ops', items: [ADMIN] }]
    : GROUPS

  const initial = (user?.full_name || user?.email || 'U').trim().charAt(0).toUpperCase()
  const plan = user?.plan ? user.plan.charAt(0).toUpperCase() + user.plan.slice(1) : ''

  const trialDaysLeft = (() => {
    if (user?.plan !== 'trial' || !user?.trial_ends_at) return null
    const ms = new Date(user.trial_ends_at).getTime() - Date.now()
    return ms <= 0 ? 0 : Math.ceil(ms / 86_400_000)
  })()

  const body = (
    <>
      <div className="h-14 flex items-center px-4 border-b border-navy-700 flex-none">
        <Logo size={24} />
      </div>

      {/* Primary action lives in the rail so it is reachable from every screen. */}
      <div className="px-3 pt-4 pb-1 flex-none">
        <Link
          to="/app/bid"
          onClick={() => setOpen(false)}
          className="btn-primary btn-sm w-full group"
        >
          Run a tender
          <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto scrollbar-thin py-4 space-y-5">
        {groups.map(g => (
          <div key={g.heading}>
            <p className="px-4 pb-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">
              {g.heading}
            </p>
            <div>
              {g.items.map(it => (
                <NavItem key={it.to} item={it} onNavigate={() => setOpen(false)} />
              ))}
            </div>
          </div>
        ))}
        <SidebarHistory onNavigate={() => setOpen(false)} />
      </nav>

      {trialDaysLeft !== null && (
        <div className="mx-3 mb-3 flex-none rounded-card border border-saffron-500/35 bg-saffron-500/10 px-3 py-2.5">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-saffron-400">
            Trial · {trialDaysLeft}d left
          </p>
        </div>
      )}

      <div className="border-t border-navy-700 px-3 py-2.5 flex-none">
        <ThemeToggle variant="segmented" onDark className="w-full justify-between" />
      </div>

      <div className="border-t border-navy-700 p-3 flex items-center gap-2.5 flex-none">
        <span className="w-8 h-8 flex-none rounded-card bg-navy-700 text-white grid place-items-center text-xs font-bold">
          {initial}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-white truncate">{user?.full_name || user?.email}</p>
          <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-fg-subtle truncate">
            {user?.company_name || plan}
          </p>
        </div>
        <button
          onClick={() => { logout(); nav('/') }}
          aria-label="Log out"
          className="p-1.5 rounded-card text-fg-subtle hover:text-white hover:bg-navy-700 transition-colors"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </>
  )

  return (
    <>
      {/* Mobile bar */}
      <div className="on-dark lg:hidden sticky top-0 z-30 h-14 bg-navy-900 border-b border-navy-700 flex items-center justify-between px-4">
        <Logo size={24} />
        <div className="flex items-center gap-1">
        <DeadlineBell state={deadlines} align="right" />
        <button
          onClick={() => setOpen(true)}
          aria-label="Open navigation"
          className="p-2 rounded-card text-white hover:bg-navy-800"
        >
          <Menu className="w-5 h-5" />
        </button>
        </div>
      </div>

      <DeadlinePopup state={deadlines} />

      {/* Mobile drawer */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <aside className="on-dark relative w-72 max-w-[84%] bg-navy-900 flex flex-col">
            <button
              onClick={() => setOpen(false)}
              aria-label="Close navigation"
              className="absolute right-3 top-3.5 p-1.5 rounded-card text-steel-400 hover:text-white z-10"
            >
              <X className="w-5 h-5" />
            </button>
            {body}
          </aside>
        </div>
      )}

      {/* Desktop rail */}
      <aside className="on-dark hidden lg:flex fixed inset-y-0 left-0 w-rail bg-navy-900 border-r border-navy-700 flex-col z-20">
        {body}
      </aside>
    </>
  )
}
