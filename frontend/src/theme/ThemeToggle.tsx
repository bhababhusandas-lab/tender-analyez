import { Sun, Moon, Monitor } from 'lucide-react'
import { useTheme, type ThemeChoice } from './ThemeContext'

/**
 * Two shapes, one state.
 *
 * `variant="switch"` — a single icon button that flips light ⇄ dark. Goes in
 * chrome where space is tight (the public header, the sidebar footer).
 *
 * `variant="segmented"` — light / system / dark, all three visible. Goes in
 * settings-ish places where the "follow my OS" option should be discoverable
 * rather than hidden behind a long-press nobody will try.
 */
export function ThemeToggle({
  variant = 'switch',
  onDark = false,
  className = '',
}: {
  variant?: 'switch' | 'segmented'
  /** Sitting on a permanently-navy ground (header, rail). */
  onDark?: boolean
  className?: string
}) {
  const { choice, resolved, setChoice, toggle } = useTheme()

  if (variant === 'segmented') {
    const OPTS: { v: ThemeChoice; icon: typeof Sun; label: string }[] = [
      { v: 'light',  icon: Sun,     label: 'Light' },
      { v: 'system', icon: Monitor, label: 'System' },
      { v: 'dark',   icon: Moon,    label: 'Dark' },
    ]
    return (
      <div
        role="radiogroup"
        aria-label="Colour theme"
        className={`inline-flex items-center gap-0.5 p-0.5 rounded-card border
          ${onDark ? 'border-navy-700 bg-navy-950' : 'border-edge bg-sunk'} ${className}`}
      >
        {OPTS.map(o => {
          const Icon = o.icon
          const on = choice === o.v
          return (
            <button
              key={o.v}
              role="radio"
              aria-checked={on}
              onClick={() => setChoice(o.v)}
              title={o.label}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-chip
                text-[11px] font-semibold transition-colors
                ${on
                  ? 'bg-saffron-600 text-white'
                  : onDark
                    ? 'text-steel-400 hover:text-white'
                    : 'text-fg-subtle hover:text-fg'}`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{o.label}</span>
            </button>
          )
        })}
      </div>
    )
  }

  const next = resolved === 'dark' ? 'light' : 'dark'
  return (
    <button
      onClick={toggle}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme${choice === 'system' ? ' (currently following your system)' : ''}`}
      className={`relative grid place-items-center w-9 h-9 rounded-card border transition-colors
        ${onDark
          ? 'border-navy-700 text-steel-400 hover:text-white hover:border-navy-600 hover:bg-navy-800'
          : 'border-edge text-fg-subtle hover:text-fg hover:bg-sunk'} ${className}`}
    >
      {/* Both icons are mounted and cross-faded, so the button never reflows
          and the swap reads as one movement rather than a pop. */}
      <Sun
        className={`absolute w-[17px] h-[17px] transition-all duration-200
          ${resolved === 'dark' ? 'opacity-0 -rotate-90 scale-75' : 'opacity-100 rotate-0 scale-100'}`}
      />
      <Moon
        className={`absolute w-[17px] h-[17px] transition-all duration-200
          ${resolved === 'dark' ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 rotate-90 scale-75'}`}
      />
    </button>
  )
}
