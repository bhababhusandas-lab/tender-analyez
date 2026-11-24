/** @type {import('tailwindcss').Config} */

/* ═══════════════════════════════════════════════════════════════════════════
   TENDER ANALYST AI — DESIGN SYSTEM v3 "Institutional"
   ───────────────────────────────────────────────────────────────────────────
   Direction: Premium · Authoritative · Conversion-aggressive.
   Sits above government portals in polish, above aggregators in sharpness,
   above generic Indian B2B SaaS in confidence.

   THREE COLOURS DO ALL THE WORK
     navy     — authority, structure, every dark ground and heading
     saffron  — action. Reserved almost entirely for CTAs and live state.
     steel    — the cool neutral scale: text, hairlines, backgrounds

   Nothing else may be introduced without a reason written next to it.
   ═══════════════════════════════════════════════════════════════════════════ */

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  // Theme is driven by an explicit attribute on <html>, not the media query, so
  // the user's choice always beats the OS. The no-flash script in index.html
  // resolves "system" to a concrete attribute before first paint.
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        // Display: geometric, tightly set. Confident, contemporary, no serifs.
        // UNIQUE TYPE — Fraunces for headlines (high-contrast editorial serif),
        // Instrument Sans for interface text.
        display: ['Fraunces', 'Georgia', 'serif'],
        sans:    ['"Instrument Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        // Every figure a bidder might check — ₹, %, dates, refs — is monospace.
        mono:    ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        // Legacy alias: `font-serif` survives in a few untouched product files.
        serif:   ['Fraunces', 'Georgia', 'serif'],
      },

      colors: {
        /* ── SEMANTIC SURFACES — the only tokens that flip with the theme.
             Defined as CSS variables in index.css. Use these for anything that
             is "a page", "a card", "a hairline" or "body text". Reach for a raw
             navy/steel value only when a surface must stay that colour in both
             themes (hero bands, the sidebar rail, the run console). ───────── */
        canvas: 'rgb(var(--canvas) / <alpha-value>)',
        panel:  'rgb(var(--panel) / <alpha-value>)',
        sunk:   'rgb(var(--sunk) / <alpha-value>)',
        edge:   { DEFAULT: 'rgb(var(--edge) / <alpha-value>)', strong: 'rgb(var(--edge-2) / <alpha-value>)' },
        fg:     {
          DEFAULT: 'rgb(var(--fg) / <alpha-value>)',
          muted:   'rgb(var(--fg-muted) / <alpha-value>)',
          subtle:  'rgb(var(--fg-subtle) / <alpha-value>)',
        },
        accent:  'rgb(var(--accent) / <alpha-value>)',
        accent2: 'rgb(var(--accent-2) / <alpha-value>)',   // the logo blue

        /* ── NAVY — authority. Dark grounds, headings, the sidebar rail. ───── */
        /* Retuned from neutral charcoal to the deep blue of the logo mark, so
           every dark ground in the product is the same blue the identity is
           built from. Still dark enough to carry white text at 15:1+. */
        navy: {
          DEFAULT: '#16130F',
          950: '#0C0B09',  // deepest — hero vignette, overlays, drawer scrim
          900: '#16130F',  // Deep Navy — headings, main text, primary dark ground
          800: '#1C1915',  // Charcoal — dark sections, raised panels on dark
          700: '#2E2A24',  // borders and hover on dark
          600: '#443E35',
          500: '#5E564A',
        },

        /* ── AZURE — the logo blue, as a UI colour. Structural and
             informational: links in prose, "submitted" state, the second series
             on a chart, the cool half of the hero bloom. It never takes an
             action — that is saffron's job and the two must not compete. ───── */
        azure: {
          DEFAULT: '#2A3FBF',
          50:  '#EEF0FC',
          100: '#DDE1F8',
          200: '#BBC3F1',
          300: '#A9B4FF',
          400: '#8C9CFF',  // dark-theme link tint — 5.7:1 on charcoal
          500: '#3A50D9',  // Bright Blue — hover states
          600: '#2A3FBF',  // Primary Blue — headers, links, icons. 6.8:1 on white
          700: '#22339B',
          800: '#1A2777',
          900: '#121B54',
        },

        /* ── SAFFRON — action. The only warm colour on the page, so it always
             means "do this". Government saffron pushed toward conversion red.
             500 = brand accent on dark grounds + graphics (5.4:1 on navy-900)
             600 = CTA fill, because white on 500 fails AA at button sizes.  */
        saffron: {
          DEFAULT: '#E0401F',
          50:  '#FDF0EB',
          100: '#FADBD0',
          200: '#F4B3A0',
          300: '#EE8A6E',
          400: '#F0583A',  // Warm Orange — secondary highlights, accent on dark
          500: '#E0401F',  // Vibrant Orange — MAIN CTA FILL (with navy text)
          600: '#C2361A',  // shade for accent TEXT on light — 4.7:1 on Light Gray
          700: '#A12C15',
          800: '#7A2110',
        },

        /* ── AMBER — secondary warm. Warnings and "expiring" state only, so it
             never competes with saffron for the eye. ───────────────────────── */
        amber: {
          50: '#FFFBEB', 100: '#FEF3C7', 300: '#FCD34D',
          500: '#F59E0B', 600: '#D97706', 700: '#B45309',
        },

        /* ── STEEL — the cool neutral. Text, hairlines, backgrounds. ───────── */
        steel: {
          DEFAULT: '#6E6455',
          950: '#0C0B09',
          900: '#16130F',  // Deep Navy — headings and main text
          800: '#2A251F',
          700: '#3D372F',
          600: '#4A4238',  // secondary text — 7.6:1 on white
          500: '#6E6455',  // Cool Gray — secondary text, 4.8:1 on white
          400: '#A39886',  // labels on dark, disabled
          300: '#C9BFAD',  // strong hairline
          200: '#DCD3C1',  // hairline
          100: '#EAE3D4',  // Light Gray — backgrounds
          50:  '#F3EEE3',  // Off White — section backgrounds
        },

        /* ── SAGE — muted supporting green. Verified / passing states, and the
             only place a second hue is allowed on a chart. ─────────────────── */
        sage: {
          50: '#F0F6F3', 100: '#DBE9E2', 300: '#8FB4A3',
          500: '#4B7C63', 600: '#3B6650', 700: '#2E5240',
        },

        /* ── STATUS — one token per meaning. Never pick a raw colour for state. */
        status: {
          ok:   '#3B6650',  // cleared, verified, won
          warn: '#B45309',  // expiring, needs attention
          risk: '#B42318',  // disqualifying, expired, lost
          info: '#2A3FBF',  // informational, submitted — Primary Blue
          idle: '#A39886',  // queued, not started
          live: '#E0401F',  // running right now
        },

        /* ── LEGACY ALIASES ────────────────────────────────────────────────────
             Roughly 800 references to the old ink, bone, brass, cream, gray and
             blue scales remain in product screens not touched by this redesign.
             Remapping them onto the new palette carries every one of those
             surfaces across without editing thirty files.
             Do not use these in new code. */
        ink: {
          DEFAULT: '#16130F',
          900: '#16130F', 800: '#1C1915', 700: '#2E2A24', 600: '#443E35',
          500: '#6E6455', 400: '#A39886', 300: '#C9BFAD', 200: '#DCD3C1',
          100: '#EAE3D4', 50: '#F3EEE3',
        },
        bone:  { DEFAULT: '#F3EEE3', 50: '#FFFFFF', 100: '#F3EEE3', 200: '#EAE3D4', 300: '#DCD3C1' },
        brass: { DEFAULT: '#C2361A', 400: '#EE8A6E', 500: '#E0401F', 600: '#C2361A', 700: '#A12C15' },
        cream: { 50: '#FFFFFF', 100: '#F3EEE3', 200: '#EAE3D4', 300: '#DCD3C1' },
        gray: {
          50: '#F3EEE3', 100: '#EAE3D4', 200: '#DCD3C1', 300: '#C9BFAD',
          400: '#A39886', 500: '#6E6455', 600: '#4A4238', 700: '#3D372F',
          800: '#2A251F', 900: '#16130F',
        },
        blue: {
          50: '#EEF0FC', 100: '#DDE1F8', 200: '#BBC3F1', 300: '#A9B4FF',
          400: '#8C9CFF', 500: '#3A50D9', 600: '#2A3FBF', 700: '#22339B',
          800: '#1A2777', 900: '#121B54',
        },
      },

      fontSize: {
        /* Display scale — Inter Tight, tight tracking, heavy weights. Built to
           hit hard above the fold and stay readable at 360px. */
        'display-2xl': ['clamp(2.375rem, 4.4vw, 3.875rem)', { lineHeight: '0.98', letterSpacing: '-0.03em', fontWeight: '600' }],
        'display-xl':  ['clamp(2rem, 3.4vw, 3rem)',         { lineHeight: '1.02', letterSpacing: '-0.026em', fontWeight: '600' }],
        'display-lg':  ['clamp(1.875rem, 3.2vw, 2.75rem)',{ lineHeight: '1.05', letterSpacing: '-0.022em', fontWeight: '600' }],
        'display-md':  ['clamp(1.375rem, 2vw, 1.75rem)',  { lineHeight: '1.12', letterSpacing: '-0.018em', fontWeight: '600' }],
        'display-sm':  ['1.125rem', { lineHeight: '1.28', letterSpacing: '-0.015em', fontWeight: '600' }],
        'lead':        ['clamp(1.0625rem, 1.15vw, 1.1875rem)', { lineHeight: '1.6' }],
        'eyebrow':     ['11px', { lineHeight: '1', letterSpacing: '0.16em', fontWeight: '600' }],
        'micro':       ['11px', { lineHeight: '1.35', letterSpacing: '0.01em' }],
      },

      spacing: { section: '4.5rem', 'section-lg': '7rem', rail: '15rem' },

      /* Small radii only. Sharp corners read as instrument, not consumer app. */
      borderRadius: { card: '2px', panel: '2px', pill: '999px', chip: '999px' },

      boxShadow: {
        // Editorial: flat sheets with a crisp printed offset, not soft glows.
        hair:   '0 1px 0 rgba(22,19,15,.08)',
        card:   '0 1px 0 rgba(22,19,15,.06)',
        raised: '4px 4px 0 rgba(22,19,15,.10)',
        deep:   '0 30px 70px -28px rgba(22,19,15,.45)',
        cta:    '3px 3px 0 #16130F',
        'cta-hover': '5px 5px 0 #16130F',
        inset:  'inset 0 1px 0 rgba(255,255,255,.06)',
      },

      maxWidth: { measure: '64ch', shell: '80rem' },

      keyframes: {
        'bar-fill':  { from: { transform: 'scaleX(0)' }, to: { transform: 'scaleX(1)' } },
        'sweep':     { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(200%)' } },
        'marquee':   { from: { transform: 'translate3d(0,0,0)' }, to: { transform: 'translate3d(-50%,0,0)' } },
        'rise':      { from: { opacity: '0', transform: 'translateY(10px)' }, to: { opacity: '1', transform: 'none' } },
      },
      animation: {
        'bar-fill':   'bar-fill 1.1s cubic-bezier(.22,1,.36,1) both',
        'sweep':      'sweep 2.4s cubic-bezier(.4,0,.2,1) infinite',
        'marquee':    'marquee 46s linear infinite',
        'rise':       'rise .5s cubic-bezier(.22,1,.36,1) both',
      },
    },
  },
  plugins: [],
}
