import { Link } from 'react-router-dom'
import { Home, ArrowLeft } from 'lucide-react'
import { Logo } from '../components/brand/Logo'

const ROUTES: [string, string][] = [
  ['/app/overview', 'Overview'],
  ['/app/bid',      'New analysis'],
  ['/app/history',  'Tender history'],
]

export function NotFound() {
  return (
    <div className="on-dark min-h-screen bg-navy-900 flex flex-col relative overflow-hidden">
      <div className="absolute inset-0 bg-grid-dark opacity-70 layer" />
      <div className="absolute inset-0 bloom-brand opacity-60 layer" />

      <header className="relative pl-3 pr-5 sm:pl-4 sm:pr-8 h-[68px] flex items-center border-b border-navy-700">
        <Logo size={38} />
      </header>

      <div className="relative flex-1 flex items-center justify-center px-5 py-16 text-center">
        <div className="max-w-lg">
          <p className="eyebrow text-saffron-500">Error 404</p>
          <p className="mt-4 font-display text-[110px] sm:text-[160px] font-bold leading-none text-white tnum tracking-tight">
            4<span className="text-saffron-500">0</span>4
          </p>
          <h1 className="mt-2 text-display-md text-white">This page is not on the register</h1>
          <p className="mt-3 text-steel-300 leading-relaxed">
            The page you asked for does not exist or has been moved. Nothing in your account
            has changed — here is the way back.
          </p>

          <div className="mt-8 flex items-center justify-center gap-3 flex-wrap">
            <button onClick={() => history.back()} className="btn-ghost-dark btn-md">
              <ArrowLeft className="w-4 h-4" /> Go back
            </button>
            <Link to="/" className="btn-primary btn-md">
              <Home className="w-4 h-4" /> Take me home
            </Link>
          </div>

          <nav className="mt-10 pt-6 border-t border-navy-700 flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
            {ROUTES.map(([to, label]) => (
              <Link
                key={to}
                to={to}
                className="font-mono text-[11px] uppercase tracking-[0.12em] text-steel-400 hover:text-saffron-500 transition-colors"
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </div>
  )
}
