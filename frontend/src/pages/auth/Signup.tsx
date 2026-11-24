import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mail, Lock, User, Building2, Phone, Loader2, AlertCircle, ArrowRight } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { AuthShell, AuthHead, AuthField, AuthFooter } from '../../components/marketing/AuthShell'

export function Signup() {
  const { signup } = useAuth()
  const nav = useNavigate()
  const [form, setForm] = useState({ email: '', password: '', full_name: '', company_name: '', phone: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const update = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value })

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      await signup(form)
      nav('/verify-email')   // email must be verified before the workspace opens
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Signup failed. Please try again.')
    } finally { setBusy(false) }
  }

  return (
    <AuthShell
      eyebrow="Free plan"
      title="Hire eleven specialists"
      accent="this afternoon."
      blurb="No card at signup, no sales call. Put a live tender through the full run and judge the platform on what it finds."
      bullets={[
        'All 11 specialists from the first minute',
        'Eligibility scoring, BOQ costing and legal review',
        'Cancel any time — nothing charged automatically',
        'Your documents are never used to train models',
      ]}
    >
      <AuthHead
        eyebrow="Create account"
        title="Start with the Free plan."
        sub="Five Bid Pipeline runs every month. No card required."
      />

      <form onSubmit={submit} className="space-y-4 panel p-6">
        <AuthField
          id="su-name" label="Full name" icon={<User className="w-4 h-4" />}
          required autoFocus autoComplete="name"
          value={form.full_name} onChange={update('full_name')} placeholder="R. Sharma"
        />
        <AuthField
          id="su-company" label="Company name" icon={<Building2 className="w-4 h-4" />}
          required autoComplete="organization"
          value={form.company_name} onChange={update('company_name')} placeholder="Sharma Infra Pvt Ltd"
        />
        <AuthField
          id="su-email" label="Work email" icon={<Mail className="w-4 h-4" />}
          type="email" required autoComplete="email"
          value={form.email} onChange={update('email')} placeholder="you@company.com"
        />
        <AuthField
          id="su-phone" label="Phone" icon={<Phone className="w-4 h-4" />}
          type="tel" autoComplete="tel"
          value={form.phone} onChange={update('phone')} placeholder="+91 98765 43210"
        />
        <AuthField
          id="su-password" label="Password" icon={<Lock className="w-4 h-4" />}
          type="password" required minLength={8} autoComplete="new-password"
          value={form.password} onChange={update('password')} placeholder="At least 8 characters"
        />

        {error && (
          <div role="alert" className="flex items-start gap-2 text-sm text-[#B42318] bg-red-50 border border-red-200 px-3 py-2.5 rounded-card">
            <AlertCircle className="w-4 h-4 flex-none mt-0.5" />{error}
          </div>
        )}

        <button type="submit" disabled={busy} className="btn-primary btn-lg w-full group">
          {busy
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <>Create free account <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" /></>}
        </button>

        <p className="text-center font-mono text-[10.5px] text-fg-subtle">
          No card required · Cancel anytime
        </p>
      </form>

      <AuthFooter prompt="Already have an account?" linkTo="/login" linkLabel="Sign in →" />
    </AuthShell>
  )
}
