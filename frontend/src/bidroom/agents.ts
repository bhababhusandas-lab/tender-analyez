/* ═══════════════════════════════════════════════════════════════════════════
   THE BID ROOM — agent roster
   ───────────────────────────────────────────────────────────────────────────
   The FULL tender-analyst-ai team — all 12 platform specialists — staff the room.
   Each role uses the Design Brief identity system (solid colour + soft chip +
   sigil) and is backed 1:1 by a real agent in the backend registry, so `id`
   IS the `/api/v1/chat` agent_id (no mapping layer needed).

   `directive` is prepended to the user's turn so the shared model answers in
   this role's voice and keeps chat-length replies (the registry prompts
   otherwise push for full multi-page document dumps).
   ═══════════════════════════════════════════════════════════════════════════ */

export type BidRoomAgentId =
  | 'bid-manager'
  | 'bid-pricing'
  | 'finance-accounts'
  | 'legal-compliance'
  | 'technical-expert'
  | 'technical-writer'
  | 'qa-reviewer'
  | 'doc-controller'
  | 'market-intelligence'
  | 'govt-relations'
  | 'admin-hr'
  | 'it-support'

export interface BidRoomAgent {
  id: BidRoomAgentId
  name: string
  role: string
  /** one-line specialty shown on the roster card */
  specialty: string
  /** example question surfaced in the roster tooltip */
  example: string
  /** existing backend agent_id for /api/v1/chat (same as id) */
  backendId: string
  /** css custom-property names defined in bidroom.css */
  solidVar: string
  softVar: string
  /** short monogram for the sigil disc */
  sigil: string
  /** compliance-critical roles carry an "assistive, not authoritative" footer */
  assistive?: boolean
  /** prepended framing so the shared model answers in-role and chat-length */
  directive: string
}

const CHAT_STYLE =
  'Answer conversationally for a live chat room: be direct and concise (a few short paragraphs at most), use plain language, and only produce tables or long checklists if the user explicitly asks. Do not dump a full document.'

const d = (role: string) => `${role} ${CHAT_STYLE}`

export const bidRoomAgents: BidRoomAgent[] = [
  {
    id: 'bid-manager', name: 'Bid Manager', role: 'Strategy & orchestration',
    specialty: 'Bid/no-go, timeline, requirements coverage, coordination',
    example: 'Should we bid, and what do we do first?',
    backendId: 'bid-manager', solidVar: '--agent-bidmgr', softVar: '--agent-bidmgr-soft', sigil: 'BM',
    directive: d('You are the Bid Manager and strategic lead. Frame the go/no-go, the win angle, requirements coverage, timeline, and who owns what.'),
  },
  {
    id: 'bid-pricing', name: 'Pricing', role: 'Win-rate pricing',
    specialty: 'Competitive L1 pricing, margin, EMD/PBG, price justification',
    example: 'How should we price this tender to win?',
    backendId: 'bid-pricing', solidVar: '--agent-pricing', softVar: '--agent-pricing-soft', sigil: 'P',
    directive: d('You are the Bid Pricing analyst. Focus on the winning price band, margin, EMD/PBG, and a defensible price justification.'),
  },
  {
    id: 'finance-accounts', name: 'Finance', role: 'Finance & tax compliance',
    specialty: 'BOQ, GST/ITR, turnover, solvency, working capital',
    example: 'What financial documents do we need?',
    backendId: 'finance-accounts', solidVar: '--agent-finance', softVar: '--agent-finance-soft', sigil: 'F',
    directive: d('You are the Finance & Accounts specialist. Cover BOQ figures, statutory documents (GST, ITR, turnover, solvency), EMD/PBG capital, and tax compliance.'),
  },
  {
    id: 'legal-compliance', name: 'Legal', role: 'Clause risk & compliance',
    specialty: 'Clause risk, eligibility, T&Cs, pre-bid queries',
    example: 'Is this penalty clause risky for us?',
    backendId: 'legal-compliance', solidVar: '--agent-legal', softVar: '--agent-legal-soft', sigil: 'L', assistive: true,
    directive: d('You are the Legal / Compliance reviewer. Flag clause risk, eligibility and compliance issues, and suggest pre-bid queries. Cite the specific clause.'),
  },
  {
    id: 'technical-expert', name: 'Technical', role: 'Technical solution',
    specialty: 'Technical specs, methodology, standards, compliance matrix',
    example: 'What technical approach should we take?',
    backendId: 'technical-expert', solidVar: '--agent-technical', softVar: '--agent-technical-soft', sigil: 'T',
    directive: d('You are the Technical Expert. Cover the technical approach, methodology, relevant standards (IS/CPWD/ISO), and how to score in technical evaluation.'),
  },
  {
    id: 'technical-writer', name: 'Writer', role: 'Proposal drafting',
    specialty: 'Proposal drafting, executive summaries, structure & tone',
    example: 'Draft the executive summary for this bid.',
    backendId: 'technical-writer', solidVar: '--agent-writer', softVar: '--agent-writer-soft', sigil: 'W',
    directive: d('You are the Writer / Proposal Designer. Produce clear, evaluator-ready proposal prose, summaries, and structure.'),
  },
  {
    id: 'qa-reviewer', name: 'QA', role: 'Completeness & sign-off',
    specialty: 'Pre-submission review, completeness, disqualification risk',
    example: 'Are we compliant with the eligibility criteria?',
    backendId: 'qa-reviewer', solidVar: '--agent-qa', softVar: '--agent-qa-soft', sigil: 'QA', assistive: true,
    directive: d('You are the QA reviewer. Check completeness and compliance, flag anything that could get the bid disqualified, and give a GO / NO-GO.'),
  },
  {
    id: 'doc-controller', name: 'Docs', role: 'Documents & submission',
    specialty: 'Required documents, checklists, formatting, portal upload',
    example: 'What documents are required and in what order?',
    backendId: 'doc-controller', solidVar: '--agent-docs', softVar: '--agent-docs-soft', sigil: 'D',
    directive: d('You are the Document Controller. Cover required documents, assembly order, annexures, formatting, and portal upload rules.'),
  },
  {
    id: 'market-intelligence', name: 'Market', role: 'Competitor & sector intel',
    specialty: 'Competitor moves, department budgets, sector trends',
    example: 'Who are our likely competitors on this?',
    backendId: 'market-intelligence', solidVar: '--agent-market', softVar: '--agent-market-soft', sigil: 'M',
    directive: d('You are the Market Intelligence analyst. Cover likely competitors, their pricing patterns, department budgets, and sector positioning.'),
  },
  {
    id: 'govt-relations', name: 'Govt Relations', role: 'Stakeholders & liaison',
    specialty: 'Department contacts, pre-bid meetings, process norms',
    example: 'How do we approach the department pre-bid?',
    backendId: 'govt-relations', solidVar: '--agent-govt', softVar: '--agent-govt-soft', sigil: 'GR',
    directive: d('You are the Govt Relations & Liaison officer. Map the relevant authorities, pre-bid meeting protocol, and process-correct approaches.'),
  },
  {
    id: 'admin-hr', name: 'Admin & HR', role: 'Manpower & compliance',
    specialty: 'Manpower credentials, PF/ESI, labour compliance',
    example: 'What manpower proof do we need to submit?',
    backendId: 'admin-hr', solidVar: '--agent-adminhr', softVar: '--agent-adminhr-soft', sigil: 'HR',
    directive: d('You are the Admin / HR specialist. Cover manpower credentials, PF/ESI thresholds, labour compliance, and personnel documents for the bid.'),
  },
  {
    id: 'it-support', name: 'IT Support', role: 'Portals, DSC & security',
    specialty: 'DSC, portal accounts, upload reliability, data security',
    example: 'Our DSC is expiring — what do we do?',
    backendId: 'it-support', solidVar: '--agent-it', softVar: '--agent-it-soft', sigil: 'IT',
    directive: d('You are IT Support. Cover DSC/e-sign, portal accounts and errors, upload reliability, and bid-data security.'),
  },
]

export const agentById = (id: BidRoomAgentId): BidRoomAgent =>
  bidRoomAgents.find((a) => a.id === id) ?? bidRoomAgents[0]

/* ── Channels (UX spec §12.1) ─────────────────────────────────────────────
   Fixed set; each channel biases routing toward a default agent. */
export interface Channel {
  id: string
  name: string
  hint: string
  /** agent the router leans toward for messages sent here */
  bias?: BidRoomAgentId
  /** example prompt chips for the empty state */
  chips: string[]
}

export const channels: Channel[] = [
  {
    id: 'general', name: 'Command Desk',
    hint: 'Ask anything — the right agent will jump in.',
    chips: ['Give me the overall strategy for this tender', 'What should we do first?', 'Who are our likely competitors?'],
  },
  {
    id: 'bids', name: 'Bid Strategy',
    hint: 'Coordination, timeline, and requirements coverage.',
    bias: 'bid-manager',
    chips: ['What do we need to submit and by when?', 'Build a submission checklist', 'What are the eligibility requirements?'],
  },
  {
    id: 'pricing', name: 'Pricing & Commercials',
    hint: 'Cost modelling, margins, competitive pricing, EMD/PBG.',
    bias: 'bid-pricing',
    chips: ['How should we price this tender?', "What's a competitive margin here?", 'What EMD and PBG will we need?'],
  },
  {
    id: 'legal', name: 'Legal & Compliance',
    hint: 'Clause risk, eligibility, terms & conditions.',
    bias: 'legal-compliance',
    chips: ['Are there any risky clauses?', 'Draft a pre-bid query', 'Are we eligible to bid?'],
  },
  {
    id: 'technical', name: 'Technical Solution',
    hint: 'Solution approach, methodology, and the written response.',
    bias: 'technical-expert',
    chips: ['Outline our technical approach', 'Draft the executive summary', 'Which standards apply here?'],
  },
  {
    id: 'docs', name: 'Documents & Submission',
    hint: 'Required documents, checklists, formatting, portals.',
    bias: 'doc-controller',
    chips: ['What documents are required?', 'Run a completeness check', 'Which annexures do we need?'],
  },
]
