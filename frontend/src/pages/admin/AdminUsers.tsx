import { useEffect, useState } from 'react'
import { Loader2, Users, FileText, Sparkles, Calendar, AlertCircle, RefreshCcw, Search, ShieldCheck, ShieldOff, Key } from 'lucide-react'
import { fetchAdminUsers, fetchAdminStats, updateUserPlan, toggleUserActive, forceVerifyUser, peekVerificationCode, AdminUserRow, AdminStats } from '../../api/admin'

const PLAN_COLORS: Record<string, string> = {
  free:         'bg-amber-100 text-amber-800 border-amber-200',
  trial:        'bg-amber-100 text-amber-800 border-amber-200',
  starter:      'bg-sky-100 text-sky-800 border-sky-200',
  growth:       'bg-emerald-100 text-emerald-800 border-emerald-200',
  professional: 'bg-ink-100 text-ink-900 border-ink-300',
  enterprise:   'bg-purple-100 text-purple-800 border-purple-200',
}

export function AdminUsers() {
  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [u, s] = await Promise.all([fetchAdminUsers(), fetchAdminStats()])
      setUsers(u); setStats(s)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to load admin data')
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const filtered = users.filter(u => {
    if (!q.trim()) return true
    const s = q.toLowerCase()
    return u.email.toLowerCase().includes(s) || u.full_name.toLowerCase().includes(s) || u.company_name.toLowerCase().includes(s)
  })

  const onPlanChange = async (id: number, plan: string) => {
    await updateUserPlan(id, plan)
    load()
  }
  const onToggleActive = async (id: number) => {
    if (!confirm('Toggle active status for this user?')) return
    await toggleUserActive(id)
    load()
  }
  const onForceVerify = async (id: number, email: string) => {
    if (!confirm(`Force-verify ${email}? This skips the email confirmation step.`)) return
    await forceVerifyUser(id)
    load()
  }
  const onPeekCode = async (id: number, email: string) => {
    const r = await peekVerificationCode(id)
    alert(`Verification code for ${email}:\n\n${r.verification_code || '(none — already verified or expired)'}`)
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <div className="flex items-center justify-between mb-7">
        <div>
          <p className="eyebrow text-ink-900">Admin · Users</p>
          <h1 className="mt-2 font-display text-3xl text-ink-900">Everyone on the platform</h1>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-2 text-sm font-medium px-3.5 py-2 border border-ink-200 rounded-lg hover:bg-ink-50 transition disabled:opacity-50">
          <RefreshCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* === Stats === */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-7">
          <StatCard icon={<Users className="w-4 h-4" />} label="Total users"      value={stats.total_users} />
          <StatCard icon={<Sparkles className="w-4 h-4" />} label="Free users"    value={stats.trial_users} />
          <StatCard icon={<Calendar className="w-4 h-4" />} label="New this week" value={stats.new_this_week} />
          <StatCard icon={<FileText className="w-4 h-4" />} label="Total bids"    value={stats.total_bids} />
        </div>
      )}

      {/* === Search === */}
      <div className="relative mb-4 max-w-md">
        <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-400" />
        <input
          type="search"
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search by email, name, or company…"
          className="w-full pl-10 pr-3.5 py-2.5 text-sm bg-panel border border-ink-200 rounded-lg focus:border-ink-800 focus:ring-2 focus:ring-ink-100 outline-none transition"
        />
      </div>

      {error && (
        <div className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2.5 rounded-lg mb-4">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />{error}
        </div>
      )}

      {loading && !users.length ? (
        <div className="flex items-center justify-center py-20 text-ink-400">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : (
        <div className="bg-panel border border-ink-200 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-cream-50 border-b border-ink-200">
                <tr className="text-left text-[11px] font-mono uppercase tracking-widest text-ink-500">
                  <th className="px-4 py-3 font-semibold">User</th>
                  <th className="px-4 py-3 font-semibold">Company</th>
                  <th className="px-4 py-3 font-semibold">Plan</th>
                  <th className="px-4 py-3 font-semibold text-center">Usage 24h / 30d</th>
                  <th className="px-4 py-3 font-semibold text-center">Bids</th>
                  <th className="px-4 py-3 font-semibold text-center">Docs</th>
                  <th className="px-4 py-3 font-semibold">Joined</th>
                  <th className="px-4 py-3 font-semibold">Last login</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold text-center">Verified</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr><td colSpan={10} className="px-4 py-12 text-center text-ink-400">No users found.</td></tr>
                )}
                {filtered.map(u => (
                  <tr key={u.id} className="border-b border-ink-100 last:border-b-0 hover:bg-cream-50/50 transition">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-ink-700 to-ink-700 text-white text-xs font-semibold flex items-center justify-center flex-shrink-0">
                          {(u.full_name || u.email).charAt(0).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <div className="font-semibold text-ink-900 truncate flex items-center gap-1.5">
                            {u.full_name || '—'}
                            {u.is_admin && <span className="text-[9px] font-mono bg-ink-100 text-ink-900 px-1.5 py-0.5 rounded">ADMIN</span>}
                          </div>
                          <div className="text-xs text-ink-500 truncate">{u.email}</div>
                          {u.phone && <div className="text-xs text-ink-400 truncate">{u.phone}</div>}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-ink-700">{u.company_name || '—'}</td>
                    <td className="px-4 py-3">
                      <select
                        value={u.plan}
                        onChange={e => onPlanChange(u.id, e.target.value)}
                        className={`text-[11px] font-mono font-semibold tracking-wider px-2 py-1 rounded-full border outline-none cursor-pointer ${PLAN_COLORS[u.plan] || 'bg-gray-100 text-gray-700 border-gray-200'}`}
                      >
                        <option value="free">FREE</option>
                        <option value="starter">STARTER</option>
                        <option value="growth">GROWTH</option>
                        <option value="professional">PROFESSIONAL</option>
                        <option value="enterprise">ENTERPRISE</option>
                      </select>
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-ink-700 text-xs whitespace-nowrap">
                      {u.usage_24h} <span className="text-ink-400">/</span> {u.usage_30d}
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-ink-700">{u.bids_count}</td>
                    <td className="px-4 py-3 text-center font-mono text-ink-700">{u.documents_count}</td>
                    <td className="px-4 py-3 text-xs text-ink-500 whitespace-nowrap">{fmtDate(u.created_at)}</td>
                    <td className="px-4 py-3 text-xs text-ink-500 whitespace-nowrap">{u.last_login_at ? fmtDate(u.last_login_at) : '—'}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => onToggleActive(u.id)}
                        className={`text-[11px] font-mono font-semibold tracking-wider px-2 py-1 rounded-full border transition ${
                          u.is_active ? 'bg-cream-100 text-ink-900 border-ink-300 hover:bg-ink-100' : 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100'
                        }`}>
                        {u.is_active ? 'ACTIVE' : 'INACTIVE'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {u.email_verified ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-mono font-semibold text-ink-900" title="Email verified">
                          <ShieldCheck className="w-3.5 h-3.5 text-ink-900" />
                        </span>
                      ) : (
                        <div className="flex items-center justify-center gap-1.5">
                          <button onClick={() => onPeekCode(u.id, u.email)} title="View pending code"
                            className="text-ink-500 hover:text-ink-900 transition p-1">
                            <Key className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => onForceVerify(u.id, u.email)} title="Force-verify"
                            className="text-amber-700 hover:text-amber-900 transition p-1">
                            <ShieldOff className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="bg-cream-50 px-4 py-2.5 border-t border-ink-200 text-xs text-ink-500">
            Showing {filtered.length} of {users.length} users
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="bg-panel border border-ink-200 rounded-xl p-4">
      <div className="flex items-center gap-2 text-ink-500">
        {icon}
        <p className="eyebrow text-ink-900">{label}</p>
      </div>
      <p className="mt-2 font-display text-3xl text-ink-900 leading-none">{value}</p>
    </div>
  )
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) +
    ' · ' + d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
}
