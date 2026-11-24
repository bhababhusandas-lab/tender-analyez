import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

/* ═══════════════════════════════════════════════════════════════════════════
   THEME
   ───────────────────────────────────────────────────────────────────────────
   Three settings, not two. "system" is the default and the one most people
   want: the app follows the OS, including when the OS flips at sunset. Picking
   light or dark pins it and stops following.

   The resolved value is written to <html data-theme>, which is what the CSS
   variables in index.css key off. The inline script in index.html applies the
   same value before first paint so there is no flash of the wrong theme.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ThemeChoice = 'light' | 'dark' | 'system'
export type Resolved = 'light' | 'dark'

const KEY = 'taa-theme'

interface Ctx {
  /** What the user chose. */
  choice: ThemeChoice
  /** What that currently resolves to. */
  resolved: Resolved
  setChoice: (c: ThemeChoice) => void
  /** Light ⇄ dark. Pins the choice — a toggle that left you on "system" would
   *  silently undo itself the next time the OS changed. */
  toggle: () => void
}

const ThemeContext = createContext<Ctx | null>(null)

function readStored(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch { /* private mode / storage disabled */ }
  return 'system'
}

const prefersDark = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-color-scheme: dark)').matches

const resolve = (c: ThemeChoice): Resolved =>
  c === 'system' ? (prefersDark() ? 'dark' : 'light') : c

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readStored)
  const [resolved, setResolved] = useState<Resolved>(() => resolve(readStored()))

  // Apply to <html> and persist.
  useEffect(() => {
    const next = resolve(choice)
    setResolved(next)
    document.documentElement.setAttribute('data-theme', next)
    try { localStorage.setItem(KEY, choice) } catch { /* ignore */ }
  }, [choice])

  // Follow the OS while the choice is "system".
  useEffect(() => {
    if (choice !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      const next: Resolved = mq.matches ? 'dark' : 'light'
      setResolved(next)
      document.documentElement.setAttribute('data-theme', next)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [choice])

  const value: Ctx = {
    choice,
    resolved,
    setChoice: setChoiceState,
    toggle: () => setChoiceState(resolve(choice) === 'dark' ? 'light' : 'dark'),
  }

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): Ctx {
  const c = useContext(ThemeContext)
  if (!c) throw new Error('useTheme must be used inside <ThemeProvider>')
  return c
}
