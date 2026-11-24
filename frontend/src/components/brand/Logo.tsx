import { Link } from 'react-router-dom'

interface LogoProps {
  iconOnly?: boolean
  size?: number
  className?: string
  /** Dark wordmark, for light grounds. Defaults to the light wordmark. */
  onLight?: boolean
  /** Render as a plain span instead of a router link (footers, auth panels). */
  static?: boolean
  /** Show the "AI BID TEAM FOR INDIAN TENDERS" line under the wordmark. */
  tagline?: boolean
}

/**
 * Unique Type identity — a typographic monogram.
 *
 * A serif "U" set on a solid block, with a vermilion full stop: the product
 * reads documents, so the mark is made of type. The wordmark follows the same
 * rule — "Unique" upright, "Type" in italic, closed with the vermilion stop.
 */
export function Logo({
  iconOnly = false,
  size = 28,
  className = '',
  onLight = false,
  static: isStatic = false,
  tagline = false,
}: LogoProps) {
  const mark = (
    <span
      role="img"
      aria-label="Unique Type"
      className={`relative flex-none inline-flex items-center justify-center rounded-[2px]
                  ${onLight ? 'bg-fg text-canvas' : 'bg-[#F3EEE3] text-[#16130F]'}`}
      style={{ width: size, height: size }}
    >
      <span
        className="font-display italic font-semibold leading-none"
        style={{ fontSize: size * 0.72, transform: 'translateY(-4%)', fontVariationSettings: '"opsz" 144, "SOFT" 50' }}
      >
        U
      </span>
      <span
        className="absolute rounded-full bg-saffron-500"
        style={{ width: size * 0.2, height: size * 0.2, right: size * 0.1, bottom: size * 0.1 }}
      />
    </span>
  )

  const wordmark = !iconOnly && (
    <span className="flex flex-col leading-none">
      <span
        className={`font-display text-[19px] leading-none tracking-[-0.02em]
                    ${onLight ? 'text-fg' : 'text-[#FBF8F1]'}`}
        style={{ fontVariationSettings: '"opsz" 72, "SOFT" 30' }}
      >
        <span className="font-semibold">Unique</span>{' '}
        <span className="italic font-normal">Type</span>
        <span className="text-saffron-500">.</span>
      </span>
      {tagline && (
        <span
          className={`mt-1.5 font-mono text-[8.5px] uppercase tracking-[0.16em] whitespace-nowrap
                      ${onLight ? 'text-fg-subtle' : 'text-steel-400'}`}
        >
          AI bid team for Indian tenders
        </span>
      )}
    </span>
  )

  const inner = <>{mark}{wordmark}</>

  if (isStatic) {
    return <span className={`flex items-center gap-2.5 ${className}`}>{inner}</span>
  }

  return (
    <Link
      to="/"
      aria-label="Unique Type home"
      className={`flex items-center gap-2.5 group transition-opacity hover:opacity-85 ${className}`}
    >
      {inner}
    </Link>
  )
}
