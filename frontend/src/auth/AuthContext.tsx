import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { api, setAuthToken, getAuthToken as readToken } from '../api/client'

export interface AuthUser {
  id: number
  email: string
  full_name: string
  company_name: string
  phone: string
  plan: string
  trial_ends_at: string | null
  is_admin: boolean
  email_verified: boolean
  created_at: string
}

interface AuthState {
  user: AuthUser | null
  token: string | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (data: SignupData) => Promise<void>
  logout: () => void
  verifyEmail: (code: string) => Promise<void>
  resendVerification: () => Promise<{ ok: boolean; message: string }>
  refreshUser: () => Promise<void>
}

interface SignupData {
  email: string
  password: string
  full_name: string
  company_name: string
  phone?: string
}

const Ctx = createContext<AuthState | undefined>(undefined)

// The deadline popup shows once per login; a new login (or logout) re-arms it.
const rearmDeadlinePopup = () => { try { sessionStorage.removeItem('taa:deadline-popup-shown') } catch { /* storage blocked */ } }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(() => readToken())
  const [loading, setLoading] = useState(true)

  // Keep the client in step with state changes that did not come through
  // login/signup/logout — e.g. a token cleared because /auth/me rejected it.
  // The authoritative write happens synchronously in those handlers; this is
  // only a safety net. It must NOT be the sole place the header is set: child
  // effects run before parent effects, so a dashboard mounted in the same
  // commit would fetch before this ran. See api/client.ts.
  useEffect(() => {
    if (readToken() !== token) setAuthToken(token)
  }, [token])

  // On mount: if we have a token, fetch /auth/me to revive the session
  useEffect(() => {
    if (!token) { setLoading(false); return }
    api.get('/api/v1/auth/me')
      .then(r => setUser(r.data))
      .catch(() => { setToken(null); setUser(null) })
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = async (email: string, password: string) => {
    const r = await api.post('/api/v1/auth/login', { email, password })
    rearmDeadlinePopup()
    setAuthToken(r.data.token)   // synchronous — before React renders the dashboard
    setToken(r.data.token)
    setUser(r.data.user)
  }

  const signup = async (data: SignupData) => {
    const r = await api.post('/api/v1/auth/signup', data)
    rearmDeadlinePopup()
    setAuthToken(r.data.token)   // synchronous — see login
    setToken(r.data.token)
    setUser(r.data.user)
  }

  const logout = () => {
    rearmDeadlinePopup()
    setAuthToken(null)
    setToken(null)
    setUser(null)
  }

  const verifyEmail = async (code: string) => {
    const r = await api.post('/api/v1/auth/verify', { code })
    setUser(r.data)
  }

  const resendVerification = async () => {
    const r = await api.post('/api/v1/auth/verify/resend')
    return r.data as { ok: boolean; message: string }
  }

  const refreshUser = async () => {
    const r = await api.get('/api/v1/auth/me')
    setUser(r.data)
  }

  return <Ctx.Provider value={{ user, token, loading, login, signup, logout, verifyEmail, resendVerification, refreshUser }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used inside <AuthProvider>')
  return v
}

/**
 * Token getter for `fetch()` callers — SSE endpoints cannot go through axios,
 * so they attach the header themselves.
 *
 * Re-exported from api/client so there is ONE source of truth. It previously
 * read localStorage directly, which could disagree with the value the axios
 * interceptor was using.
 */
export { getAuthToken } from '../api/client'
