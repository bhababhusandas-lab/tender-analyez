import { Crown, Loader2 } from 'lucide-react'
import { MarkdownReport } from './MarkdownReport'

interface FinalQuoteCardProps {
  loading: boolean
  content?: string
}

export function FinalQuoteCard({ loading, content }: FinalQuoteCardProps) {
  return (
    <div className="border-2 border-fg rounded-2xl overflow-hidden shadow-lg">
      {/* Header */}
      <div className="on-dark bg-navy-900 px-5 py-4 flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-white/10 flex items-center justify-center">
          <Crown className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="font-bold text-white text-sm">MD Briefing — Final Recommendation</p>
          <p className="text-xs text-fg-subtle">Managing Director · Unique Type</p>
        </div>
        {loading && (
          <div className="ml-auto flex items-center gap-2 text-fg-subtle">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-xs">Preparing final brief…</span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="bg-panel px-5 py-5">
        {loading && !content && (
          <div className="flex items-center gap-3 py-6 justify-center text-fg-subtle">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-sm">Your AI team is preparing the final MD briefing…</span>
          </div>
        )}
        {content && (
          <MarkdownReport content={content} />
        )}
      </div>
    </div>
  )
}
