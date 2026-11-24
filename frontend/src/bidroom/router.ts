/* ═══════════════════════════════════════════════════════════════════════════
   THE BID ROOM — intent router (the heart of the product, PRD §5.2 / TRD §6.2)
   ───────────────────────────────────────────────────────────────────────────
   Classifies a user message → the best-fit agent(s) across the full 12-agent
   team. The TRD offers "single LLM classifier vs. embeddings + rules hybrid";
   this is the rules hybrid — instant, zero-cost, explainable. Swap `routeMessage`
   for a Haiku structured-output call later without touching the UI.

   • an explicit @mention overrides the classifier entirely
   • the active channel biases the decision
   • strategic prompts pull in a small panel (cap 3), ending in one recommendation
   • routing is explainable — every result carries a human-readable `reason`
   ═══════════════════════════════════════════════════════════════════════════ */

import { BidRoomAgentId, Channel } from './agents'

export interface RouteResult {
  agentIds: BidRoomAgentId[]
  multiAgent: boolean
  confidence: number
  reason: string
}

interface Rule {
  id: BidRoomAgentId
  patterns: RegExp[]
}

const RULES: Rule[] = [
  { id: 'bid-pricing', patterns: [/\bpric(e|ing)\b/, /\bmargin\b/, /\bquote\b/, /\brate[s]?\b/, /\bL1\b/, /\bhow much\b/, /\bcompetitive\b/, /\bwin (price|zone)\b/, /\bunderbid\b/] },
  { id: 'finance-accounts', patterns: [/\bboq\b/, /\bgst\b/, /\bitr\b/, /\bturnover\b/, /\bsolvency\b/, /\bbalance sheet\b/, /\btax\b/, /\btds\b/, /\bworking capital\b/, /\bemd\b/, /\bpbg\b/, /\bfinancial (statement|document|bid)\b/, /₹|\brupee|\binr\b/] },
  { id: 'legal-compliance', patterns: [/\bclause/, /\blegal/, /\bcomplian(t|ce)/, /\beligib/, /\bpenalt/, /\bliab/, /\brisk/, /\bterms?\b/, /\bt&c\b/, /\bcontract/, /\barbitrat/, /\bblacklist/, /\bindemnif/, /\bpre-?bid quer/, /\bgfr\b/, /\bcvc\b/] },
  { id: 'technical-writer', patterns: [/\bdraft\b/, /\bwrite\b/, /\bexecutive summary\b/, /\bproposal (text|prose|draft)\b/, /\bnarrative\b/, /\bcover letter\b/, /\btone\b/, /\bword(ing)?\b/, /\bformat the (proposal|response)\b/] },
  { id: 'technical-expert', patterns: [/\btechnical (approach|response|spec|solution|write)/, /\bmethodolog/, /\bis code/, /\bcpwd\b/, /\bstandard[s]?\b/, /\barchitecture\b/, /\bsolution design\b/, /\bcompliance matrix\b/, /\bspecification/] },
  { id: 'qa-reviewer', patterns: [/\bqa\b/, /\bquality\b/, /\bcheck(list)?\b/, /\bcomplete(ness)?\b/, /\bmissing\b/, /\bdisqualif/, /\bverify\b/, /\bsign-?off\b/, /\bbefore (we )?submit/, /\bfinal review\b/, /\bgo\/no-?go\b/] },
  { id: 'doc-controller', patterns: [/\bdocument[s]?\b/, /\bannexure/, /\bupload\b/, /\bportal\b/, /\bformat(ting)?\b/, /\bpage number/, /\bassembl/, /\bfile (size|format)\b/, /\bsubmission (order|pack)/, /\bdeclaration/, /\bundertaking/] },
  { id: 'market-intelligence', patterns: [/\bcompetitor/, /\bmarket\b/, /\bwho (won|wins|else is bidding)\b/, /\bbudget allocation\b/, /\bsector\b/, /\bintel(ligence)?\b/, /\blandscape\b/, /\bwho are we up against\b/] },
  { id: 'govt-relations', patterns: [/\bliaison\b/, /\bdepartment\b/, /\bofficial[s]?\b/, /\brelationship\b/, /\bpre-?bid meeting\b/, /\bpwd\b/, /\bghmc\b/, /\bnic\b/, /\bstakeholder/, /\bnodal officer\b/, /\bempanel/] },
  { id: 'admin-hr', patterns: [/\bmanpower\b/, /\bpf\b/, /\besi\b/, /\bemployee[s]?\b/, /\bstaff(ing)?\b/, /\bcv[s]?\b/, /\bresume[s]?\b/, /\blabour\b/, /\bpersonnel\b/, /\bexperience letter/, /\bpayroll\b/] },
  { id: 'it-support', patterns: [/\bdsc\b/, /\bdigital signature\b/, /\be-?sign\b/, /\bportal (down|error|login)\b/, /\bupload fail/, /\bcertificate expir/, /\btoken\b/, /\b2fa\b/, /\bencrypt/, /\blogin (issue|problem)\b/] },
  { id: 'bid-manager', patterns: [/\btimeline\b/, /\bdeadline\b/, /\bmilestone\b/, /\bcoordinat/, /\bwho (does|should|owns)\b/, /\bplan\b/, /\bschedule\b/, /\bnext step/, /\brequirements?\b/, /\bcoverage\b/, /\bwhat.* need to submit/, /\bshould we bid\b/, /\bbid\/no-?bid\b/] },
]

/** Strategic prompts that should pull in a small panel (PRD §5.3). */
const STRATEGIC = [
  /\bstrateg/, /\bgo\/no-?go\b/, /\bbid\/no-?bid\b/, /\bshould we bid\b/, /\boverall\b/, /\bwin (this|the|more)\b/,
  /\bprioriti[sz]/, /\bwhat.* do first\b/, /\bgame ?plan\b/, /\bbig picture\b/, /\bwhere do we (start|begin)\b/,
]

/** Max agents that may collaborate on one turn (PRD caps pile-ons; raised to 4). */
const MAX_PANEL = 4

/** Fixed multi-agent recipes for common strategic asks (TRD §6.3), led by Bid Manager. */
function strategicPanel(text: string): BidRoomAgentId[] {
  if (/\beligib|complian|qualif/.test(text)) return ['bid-manager', 'legal-compliance', 'qa-reviewer', 'doc-controller']
  if (/\bpric|cost|margin|quote|win price/.test(text)) return ['bid-manager', 'bid-pricing', 'finance-accounts', 'market-intelligence']
  if (/\bcompetitor|market|who.*(win|bidding|against)/.test(text)) return ['bid-manager', 'market-intelligence', 'bid-pricing', 'govt-relations']
  if (/\btechnical|methodolog|solution/.test(text)) return ['bid-manager', 'technical-expert', 'technical-writer', 'qa-reviewer']
  return ['bid-manager', 'technical-expert', 'bid-pricing', 'qa-reviewer']
}

const MENTION_MAP: Record<string, BidRoomAgentId> = {
  'bid manager': 'bid-manager', bidmanager: 'bid-manager', 'bid-manager': 'bid-manager', bidmgr: 'bid-manager', bm: 'bid-manager',
  pricing: 'bid-pricing', price: 'bid-pricing',
  finance: 'finance-accounts', accounts: 'finance-accounts',
  legal: 'legal-compliance', compliance: 'legal-compliance',
  technical: 'technical-expert', tech: 'technical-expert',
  writer: 'technical-writer', write: 'technical-writer',
  qa: 'qa-reviewer', quality: 'qa-reviewer',
  docs: 'doc-controller', doc: 'doc-controller', documents: 'doc-controller',
  market: 'market-intelligence',
  govt: 'govt-relations', 'govt relations': 'govt-relations', government: 'govt-relations', liaison: 'govt-relations',
  admin: 'admin-hr', hr: 'admin-hr', 'admin & hr': 'admin-hr', 'admin hr': 'admin-hr',
  it: 'it-support', 'it support': 'it-support',
}

/** Extract an @mention override, if any. Returns the agent id or null. */
export function parseMention(text: string): BidRoomAgentId | null {
  const m = text.match(/@([a-z][a-z&\s-]*?)(?=[\s,.:!?]|$)/i)
  if (!m) return null
  const key = m[1].trim().toLowerCase()
  if (MENTION_MAP[key]) return MENTION_MAP[key]
  // fall back to the longest matching prefix (e.g. "@Govt" → govt-relations)
  const hit = Object.keys(MENTION_MAP).find((k) => k.startsWith(key) && key.length >= 2)
  return hit ? MENTION_MAP[hit] : null
}

const AGENT_LABEL: Record<BidRoomAgentId, string> = {
  'bid-manager': 'Bid Manager',
  'bid-pricing': 'Pricing',
  'finance-accounts': 'Finance',
  'legal-compliance': 'Legal',
  'technical-expert': 'Technical',
  'technical-writer': 'Writer',
  'qa-reviewer': 'QA',
  'doc-controller': 'Docs',
  'market-intelligence': 'Market',
  'govt-relations': 'Govt Relations',
  'admin-hr': 'Admin & HR',
  'it-support': 'IT Support',
}

export function routeMessage(text: string, channel: Channel): RouteResult {
  const lower = text.toLowerCase()

  // 1) explicit @mention wins outright
  const mentioned = parseMention(text)
  if (mentioned) {
    return { agentIds: [mentioned], multiAgent: false, confidence: 1, reason: `You addressed ${AGENT_LABEL[mentioned]} directly` }
  }

  // 2) explicitly strategic → fixed multi-agent recipe
  if (STRATEGIC.some((re) => re.test(lower))) {
    const panel = strategicPanel(lower).slice(0, MAX_PANEL)
    return {
      agentIds: panel,
      multiAgent: true,
      confidence: 0.8,
      reason: `Strategic question — combining ${panel.map((id) => AGENT_LABEL[id]).join(', ')}`,
    }
  }

  // 3) score every rule by keyword hits (channel bias tracked separately so a
  //    bias alone never fabricates a second collaborator)
  const kw = new Map<BidRoomAgentId, number>()
  for (const rule of RULES) {
    let s = 0
    for (const p of rule.patterns) if (p.test(lower)) s += 1
    if (s > 0) kw.set(rule.id, s)
  }

  // 4) how many DISTINCT domains did the question touch?
  const engaged = [...kw.entries()].sort((a, b) => b[1] - a[1])

  // 4a) multi-domain question → the relevant specialists collaborate (up to
  //     MAX_PANEL). Bid Manager then synthesises one "Team recommendation" at
  //     the end (see orchestrator), so it need not occupy a panel slot itself.
  if (engaged.length >= 2) {
    const panel = engaged.slice(0, MAX_PANEL).map(([id]) => id)
    // if Bid Manager is itself one of the matched specialists, let it lead
    const ordered: BidRoomAgentId[] = panel.includes('bid-manager')
      ? ['bid-manager', ...panel.filter((id) => id !== 'bid-manager')]
      : panel
    return {
      agentIds: ordered,
      multiAgent: true,
      confidence: 0.75,
      reason: `Spans ${ordered.length} areas — combining ${ordered.map((id) => AGENT_LABEL[id]).join(', ')}`,
    }
  }

  // 4b) single clear domain
  if (engaged.length === 1) {
    const [topId, topScore] = engaged[0]
    const biased = channel.bias === topId ? ` (${channel.name} bias)` : ''
    return {
      agentIds: [topId],
      multiAgent: false,
      confidence: Math.min(0.98, 0.6 + topScore * 0.1),
      reason: `Matched ${AGENT_LABEL[topId]} on topic${biased}`,
    }
  }

  // 4c) no signal → channel default, else Bid Manager
  const fallback: BidRoomAgentId = channel.bias ?? 'bid-manager'
  return {
    agentIds: [fallback],
    multiAgent: false,
    confidence: 0.4,
    reason: channel.bias
      ? `No clear signal — defaulting to ${channel.name}'s ${AGENT_LABEL[fallback]}`
      : `No clear signal — defaulting to ${AGENT_LABEL[fallback]}`,
  }
}
