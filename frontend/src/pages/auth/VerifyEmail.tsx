import { useState, useEffect, useRef, ClipboardEvent, KeyboardEvent, ChangeEvent, FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Mail, Loader2, AlertCircle, RefreshCcw, ArrowRight, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { AuthShell, AuthHead } from '../../components/marketing/AuthShell'

const CODE_LEN = 6
const RESEND_SECONDS = 30

export function VerifyEmail() {
  const { user, loading, verifyEmail, resendVerification, logout } = useAuth()
  const nav = useNavigate()

  const [digits, setDigits] = useState<string[]>(Array(CODE_LEN).fill(''))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [resendIn, setResendIn] = useState(0)
  const inputs = useRef<(HTMLInputElement | null)[]>([])

  // Countdown for resend cooldown
  useEffect(() => {
    if (resendIn <= 0) return
    const t = setTimeout(() => setResendIn(s => s - 1), 1000)
    return () => clearTimeout(t)
  }, [resendIn])

  // Focus first input on mount
  useEffect(() => { inputs.current[0]?.focus() }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-accent" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (user.email_verified) return <Navigate to="/app/overview" replace />

  const handleChange = (i: number, e: ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value.replace(/\D/g, '').slice(-1) // last char only
    const next = [...digits]
    next[i] = v
    setDigits(next)
    setError('')
    if (v && i < CODE_LEN - 1) inputs.current[i + 1]?.focus()
    // Auto-submit when full
    if (next.every(d => d !== '') && i === CODE_LEN - 1) {
      submitCode(next.join(''))
    }
  }

  const handleKey = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !digits[i] && i > 0) {
      inputs.current[i - 1]?.focus()
    } else if (e.key === 'ArrowLeft' && i > 0) {
      inputs.current[i - 1]?.focus()
    } else if (e.key === 'ArrowRight' && i < CODE_LEN - 1) {
      inputs.current[i + 1]?.focus()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      submitCode(digits.join(''))
    }
  }

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault()
    const text = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, CODE_LEN)
    if (!text) return
    const next = text.split('').concat(Array(CODE_LEN).fill('')).slice(0, CODE_LEN)
    setDigits(next)
    const lastIdx = Math.min(text.length - 1, CODE_LEN - 1)
    inputs.current[lastIdx]?.focus()
    if (text.length === CODE_LEN) submitCode(text)
  }

  const submitCode = async (code: string) => {
    if (busy) return
    if (code.length !== CODE_LEN) { setError('Enter all 6 digits.'); return }
    setBusy(true); setError(''); setInfo('')
    try {
      await verifyEmail(code)
      setInfo('Verified! Redirecting…')
      setTimeout(() => nav('/app/overview'), 800)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Verification failed. Please try again.')
      // Clear inputs so they can retry
      setDigits(Array(CODE_LEN).fill(''))
      inputs.current[0]?.focus()
    } finally { setBusy(false) }
  }

  const doResend = async () => {
    setError(''); setInfo('')
    try {
      const r = await resendVerification()
      setInfo(r.message ?? 'A new code has been sent.')
      setResendIn(RESEND_SECONDS)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not send a new code. Try again in a moment.')
    }
  }

  const formSubmit = (e: FormEvent) => { e.preventDefault(); submitCode(digits.join('')) }

  return (
    <AuthShell
      eyebrow="One step left"
      title="Verify your email to"
      accent="open the workspace."
      blurb="We sent a six-digit code to your inbox. It keeps your tender documents bound to an address you actually control."
      bullets={[
        'The code expires in 15 minutes',
        'Check spam if it has not arrived in a minute',
        'You can request a new one at any time',
        'Nothing is charged during the trial',
      ]}
    >
      <AuthHead
        eyebrow="Verify email"
        title="Enter your code."
        sub={`Sent to ${user.email}`}
      />

      <form onSubmit={formSubmit} className="panel p-6">
        <label className="block font-mono text-[10px] uppercase tracking-[0.14em] text-fg-subtle mb-2.5">
          Six-digit code
        </label>
        <div className="flex gap-2 justify-between">
          {digits.map((d, i) => (
            <input
              key={i}
              ref={el => (inputs.current[i] = el)}
              value={d}
              onChange={e => handleChange(i, e)}
              onKeyDown={e => handleKey(i, e)}
              onPaste={handlePaste}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={1}
              aria-label={`Digit ${i + 1}`}
              className="w-full aspect-square max-w-[3.25rem] text-center font-mono text-xl font-semibold
                         bg-panel border border-edge-strong rounded-card text-fg outline-none
                         transition-colors focus:border-saffron-500"
            />
          ))}
        </div>

        {error && (
          <div role="alert" className="mt-4 flex items-start gap-2 text-sm text-[#B42318] bg-red-50 border border-red-200 px-3 py-2.5 rounded-card">
            <AlertCircle className="w-4 h-4 flex-none mt-0.5" />{error}
          </div>
        )}
        {info && (
          <div role="status" className="mt-4 flex items-start gap-2 text-sm text-sage-700 bg-sage-50 border border-sage-300 px-3 py-2.5 rounded-card">
            <CheckCircle2 className="w-4 h-4 flex-none mt-0.5" />{info}
          </div>
        )}

        <button type="submit" disabled={busy} className="mt-5 btn-primary btn-lg w-full group">
          {busy
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <>Verify and continue <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" /></>}
        </button>

        <div className="mt-4 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={doResend}
            disabled={resendIn > 0}
            className="inline-flex items-center gap-1.5 text-[13px] font-medium text-accent
                       hover:text-saffron-700 disabled:text-steel-400 transition-colors"
          >
            <RefreshCcw className="w-3.5 h-3.5" />
            {resendIn > 0 ? `Resend in ${resendIn}s` : 'Send a new code'}
          </button>
          <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] text-fg-subtle">
            <Mail className="w-3.5 h-3.5" />{user.email}
          </span>
        </div>
      </form>

      <p className="mt-6 text-center">
        <button
          onClick={() => { logout(); nav('/login') }}
          className="font-mono text-[11px] text-fg-subtle hover:text-fg transition-colors"
        >
          ← Sign out and use a different account
        </button>
      </p>
    </AuthShell>
  )
}
