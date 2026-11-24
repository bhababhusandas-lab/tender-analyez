import axios from 'axios'

declare global {
  interface Window { API_URL?: string }
}

const BASE = window.API_URL ?? import.meta.env.VITE_API_URL ?? ''

export const api = axios.create({ baseURL: BASE })


export const apiUrl = (path: string) => `${BASE}${path}`

/* ═══════════════════════════════════════════════════════════════════════════
   AUTH TOKEN
   ───────────────────────────────────────────────────────────────────────────
   The token is held in a module variable and attached by a request
   interceptor, NOT by writing `api.defaults.headers` from a React effect.

   Why it matters: React flushes child effects BEFORE parent effects. Setting
   the header in AuthProvider's effect meant that on a fresh login, the
   dashboard mounted and fired its data calls from its own effect first — with
   no Authorization header — and every one came back 401. The screen then
   rendered empty states instead of the user's data.

   It only worked after a page reload, because `loading` gates rendering until
   /auth/me resolves, by which point the header had been set. That is exactly
   the kind of bug that hides during manual testing.

   `setAuthToken` is called synchronously the moment a token is received, so
   any request issued in the same tick already carries it.
   ═══════════════════════════════════════════════════════════════════════════ */

const TOKEN_KEY = 'taa_token'

let authToken: string | null = (() => {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
})()

export function setAuthToken(token: string | null): void {
  authToken = token
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* private mode — in-memory token still works for this session */ }
}

export function getAuthToken(): string | null {
  return authToken
}

api.interceptors.request.use(config => {
  if (authToken) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${authToken}`
  }
  return config
})
