import {
  FileText,
  Shield,
  ClipboardList,
  Scale,
  Briefcase,
  Users,
  Monitor,
  Crown,
  TrendingUp,
  Landmark,
  PenTool,
  BarChart3,
  BadgeCheck,
} from 'lucide-react'

interface AgentIconProps {
  type: string
  className?: string
}

export function AgentIcon({ type, className = 'w-5 h-5' }: AgentIconProps) {
  const props = { className }
  switch (type) {
    case 'file-text': return <FileText {...props} />
    case 'shield': return <Shield {...props} />
    case 'clipboard-list': return <ClipboardList {...props} />
    case 'scale': return <Scale {...props} />
    case 'briefcase': return <Briefcase {...props} />
    case 'users': return <Users {...props} />
    case 'monitor': return <Monitor {...props} />
    case 'crown': return <Crown {...props} />
    case 'trending-up': return <TrendingUp {...props} />
    case 'landmark': return <Landmark {...props} />
    case 'pen-tool': return <PenTool {...props} />
    case 'bar-chart': return <BarChart3 {...props} />
    case 'badge-check': return <BadgeCheck {...props} />
    default: return <FileText {...props} />
  }
}
