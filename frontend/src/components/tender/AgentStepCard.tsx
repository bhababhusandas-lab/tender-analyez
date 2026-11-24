import { Loader2, CheckCircle, AlertCircle, ChevronDown, ChevronUp, Square } from 'lucide-react'
import { AgentIcon } from '../shared/AgentIcon'
import { useState } from 'react'
import { MarkdownReport } from './MarkdownReport'

export type StepStatus = 'waiting' | 'processing' | 'done' | 'error' | 'cancelled'

interface AgentStepCardProps {
  agentId: string
  agentName: string
  iconType: string
  status: StepStatus
  content?: string
  stepNumber: number
  onRetry?: () => void
}

export function AgentStepCard({ agentId, agentName, iconType, status, content, stepNumber, onRetry }: AgentStepCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`overflow-hidden rounded-lg border bg-panel transition-all duration-300 ${
      status === 'waiting' ? 'border-edge opacity-55' :
      status === 'processing' ? 'border-fg-subtle shadow-[0_4px_18px_-12px_rgba(15,23,42,.45)]' :
      status === 'error' ? 'border-red-500/40' :
      status === 'cancelled' ? 'border-edge-strong opacity-75' :
      'border-edge shadow-[0_3px_14px_-12px_rgba(15,23,42,.35)]'
    }`}>
      {/* Header row */}
      <div
        className={`flex items-center gap-3 px-4 py-3.5 ${status === 'done' ? 'cursor-pointer hover:bg-sunk/70' : ''}`}
        onClick={() => status === 'done' && setExpanded((e) => !e)}
      >
        {/* Step number */}
        <span className={`text-xs font-bold w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
          status === 'waiting' ? 'bg-edge text-fg-subtle' :
          status === 'processing' ? 'bg-fg text-canvas' :
          status === 'error' ? 'bg-red-500 text-white' :
          status === 'cancelled' ? 'bg-fg-subtle text-canvas' :
          'bg-fg text-canvas'
        }`}>
          {stepNumber}
        </span>

        {/* Icon */}
        <div className={`w-8 h-8 rounded-md border flex items-center justify-center flex-shrink-0 ${
          status === 'waiting' ? 'border-edge bg-sunk' : 'border-edge bg-sunk'
        }`}>
          <AgentIcon
            type={iconType}
            className={`w-4 h-4 ${status === 'waiting' ? 'text-edge-strong' : 'text-fg-muted'}`}
          />
        </div>

        {/* Name */}
        <span className={`font-medium text-sm flex-1 ${status === 'waiting' ? 'text-fg-subtle' : 'text-fg'}`}>
          {agentName}
        </span>

        {/* Status */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {status === 'waiting' && <span className="text-xs text-fg-subtle">Waiting…</span>}
          {status === 'processing' && (
            <div className="flex items-center gap-1.5 text-fg-muted">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span className="text-xs font-semibold">Analyzing…</span>
            </div>
          )}
          {status === 'done' && (
            <div className="flex items-center gap-1.5 text-emerald-700">
              <CheckCircle className="w-4 h-4" />
              <span className="text-xs font-medium">Complete</span>
              {expanded ? <ChevronUp className="w-3.5 h-3.5 ml-1 text-fg-subtle" /> : <ChevronDown className="w-3.5 h-3.5 ml-1 text-fg-subtle" />}
            </div>
          )}
          {status === 'error' && (
            <div className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
              <AlertCircle className="w-4 h-4" />
              <span className="text-xs font-medium">Error</span>
              {onRetry && (
                <button type="button" onClick={(event) => { event.stopPropagation(); onRetry() }}
                  className="ml-2 rounded-md border border-red-500/30 bg-panel px-2 py-1 text-[11px] font-semibold text-red-700 dark:text-red-300 hover:bg-red-500/10">
                  Retry
                </button>
              )}
            </div>
          )}
          {status === 'cancelled' && (
            <div className="flex items-center gap-1.5 text-fg-subtle">
              <Square className="w-3.5 h-3.5 fill-current" />
              <span className="text-xs font-medium">Stopped</span>
            </div>
          )}
        </div>
      </div>

      {status === 'error' && (
        <div role="alert" className="px-4 pb-4 text-sm text-red-700 dark:text-red-300 break-words">
          {content || 'The agent could not complete its analysis. Please try again.'}
        </div>
      )}

      {/* Full detailed analysis — every section shown */}
      {status === 'done' && expanded && content && (
        <div className="px-4 pb-4 border-t border-edge pt-3">
          <MarkdownReport content={content} />
        </div>
      )}
    </div>
  )
}
