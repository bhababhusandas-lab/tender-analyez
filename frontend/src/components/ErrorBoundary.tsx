import { Component, ErrorInfo, ReactNode } from 'react'
import { AlertTriangle, RefreshCw, Home } from 'lucide-react'

interface Props { children: ReactNode }
interface State { error: Error | null }

/**
 * Top-level React error boundary.
 * Catches any uncaught render error so users never see a blank white page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Send to analytics / error tracker — best effort
    try {
      // eslint-disable-next-line no-console
      console.error('[ErrorBoundary]', error, info.componentStack)
      const w: any = window
      if (typeof w.posthog?.capture === 'function') {
        w.posthog.capture('frontend_error', {
          message: error.message,
          stack: (error.stack ?? '').slice(0, 2000),
          component_stack: (info.componentStack ?? '').slice(0, 2000),
          url: window.location.href,
        })
      }
    } catch { /* swallow */ }
  }

  reset = () => this.setState({ error: null })

  render() {
    if (!this.state.error) return this.props.children

    // Plain anchors, never react-router <Link>. This boundary is mounted ABOVE
    // <BrowserRouter> in App.tsx, so a <Link> here throws "useHref may be used
    // only in the context of a <Router>" — the fallback would crash on render
    // and hand the user the blank page the boundary exists to prevent. A hard
    // navigation is also the right behaviour after an unrecoverable error.
    return (
      <div className="min-h-screen bg-navy-900 flex items-center justify-center px-5 py-16">
        <div className="max-w-lg w-full bg-panel border border-edge rounded-panel shadow-deep p-8 text-center">
          <span className="inline-grid place-items-center w-14 h-14 rounded-card bg-red-50 text-[#B42318] border border-red-200">
            <AlertTriangle className="w-7 h-7" />
          </span>
          <h1 className="mt-5 font-display text-[22px] font-bold text-fg">
            Something went wrong on this page.
          </h1>
          <p className="mt-3 text-sm text-fg-muted leading-relaxed">
            The error was caught before the page crashed. Reload, or head back to the home page —
            your bids and documents are unaffected.
          </p>

          {import.meta.env.DEV && (
            <pre className="mt-4 text-left text-[11px] bg-sunk text-fg-muted px-3 py-2 rounded-card font-mono overflow-x-auto max-h-40">
              {this.state.error.message}
              {this.state.error.stack ? '\n' + this.state.error.stack.slice(0, 800) : ''}
            </pre>
          )}

          <div className="mt-7 flex items-center justify-center gap-3 flex-wrap">
            <button
              onClick={() => { this.reset(); window.location.reload() }}
              className="btn-primary btn-md"
            >
              <RefreshCw className="w-4 h-4" /> Reload page
            </button>
            <a href="/" className="btn-ghost btn-md">
              <Home className="w-4 h-4" /> Take me home
            </a>
          </div>
        </div>
      </div>
    )
  }
}
