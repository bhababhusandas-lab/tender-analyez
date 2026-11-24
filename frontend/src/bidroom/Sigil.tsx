import { BidRoomAgent } from './agents'

/* The signature identity element (Design Brief §9): a geometric monogram on a
   soft-tint disc with a solid-colour ring, optionally with a presence dot.
   Consistent across roster, bubbles, and dashboard stacks. */
export function Sigil({
  agent,
  size = 32,
  presence = false,
}: {
  agent: BidRoomAgent
  size?: number
  presence?: boolean
}) {
  const solid = `var(${agent.solidVar})`
  const soft = `var(${agent.softVar})`
  const dot = Math.max(8, Math.round(size * 0.3))
  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: size, height: size, flexShrink: 0 }}>
      <span
        aria-hidden
        style={{
          width: size,
          height: size,
          borderRadius: '50%',
          background: soft,
          boxShadow: `inset 0 0 0 2px ${solid}`,
          color: solid,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-display)',
          fontWeight: 600,
          fontSize: size * 0.42,
          lineHeight: 1,
          letterSpacing: '-.02em',
        }}
      >
        {agent.sigil}
      </span>
      {presence && (
        <span
          className="br-presence-dot"
          aria-hidden
          style={{
            position: 'absolute',
            right: -1,
            bottom: -1,
            width: dot,
            height: dot,
            borderRadius: '50%',
            background: 'var(--success)',
            boxShadow: '0 0 0 2px var(--surface)',
          }}
        />
      )}
    </span>
  )
}
