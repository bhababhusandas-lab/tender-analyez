import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mail, Lock, Loader2, AlertCircle, ArrowRight } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { AuthShell, AuthHead, AuthField, AuthFooter } from '../../components/marketing/AuthShell'

export function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      await login(email, password)
      // AppLayout redirects to /verify-email if the account is not verified.
      nav('/app/overview')
    } catch (err: any) {
      // Distinguish a real credential rejection from the server being unreachable
      // (e.g. the backend isn't running) so the message is actionable.
      const detail = err?.response?.data?.detail
      if (detail) {
        setError(detail)                                  // e.g. "Invalid email or password"
      } else if (err?.response) {
        setError('Something went wrong signing in. Please try again.')
      } else {
        setError('Cannot reach the server. Make sure the backend is running, then try again.')
      }
    } finally { setBusy(false) }
  }

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Your bid team is"
      accent="standing by."
      blurb="Eleven specialists — Bid Manager, Technical, Legal, Finance, QA and the rest — ready to take any tender from RFP to contract."
      bullets={[
        'Zero-defect audit before every submission',
        '7-phase analysis from Hunt to Execute',
        'Document Vault with expiry tracking',
        'Built for GeM, CPPP, IREPS and state portals',
      ]}
    >
      <AuthHead eyebrow="Sign in" title="Welcome back." sub="Pick up where you left off." />

      <form onSubmit={submit} className="space-y-4 panel p-6">
        <AuthField
          id="login-email" label="Email address" icon={<Mail className="w-4 h-4" />}
          type="email" required autoFocus autoComplete="email"
          value={email} onChange={e => setEmail(e.target.value)}
          placeholder="you@company.com"
        />
        <AuthField
          id="login-password" label="Password" icon={<Lock className="w-4 h-4" />}
          type="password" required autoComplete="current-password"
          value={password} onChange={e => setPassword(e.target.value)}
          placeholder="••••••••"
        />

        {error && (
          <div role="alert" className="flex items-start gap-2 text-sm text-[#B42318] bg-red-50 border border-red-200 px-3 py-2.5 rounded-card">
            <AlertCircle className="w-4 h-4 flex-none mt-0.5" />{error}
          </div>
        )}

        <button type="submit" disabled={busy} className="btn-primary btn-lg w-full group">
          {busy
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <>Sign in <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" /></>}
        </button>
      </form>

      <AuthFooter prompt="New here?" linkTo="/signup" linkLabel="Create a free account →" />
    </AuthShell>
  )
}
