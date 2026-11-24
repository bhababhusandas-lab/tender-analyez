import type { ReactNode } from 'react'

interface MarkdownReportProps {
  content: string
}

function inline(text: string): ReactNode[] {
  const clean = text.replace(/\\\*/g, '*')
  const output: ReactNode[] = []
  let cursor = 0
  const pattern = /\*\*([^*]+?)\*\*/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(clean)) !== null) {
    if (match.index > cursor) output.push(clean.slice(cursor, match.index).replace(/\*+/g, ''))
    output.push(<strong key={`strong-${match.index}`} className="font-semibold text-slate-900">{match[1]}</strong>)
    cursor = match.index + match[0].length
  }
  if (cursor < clean.length) output.push(clean.slice(cursor).replace(/\*+/g, ''))
  return output
}

function cells(line: string) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
}

function isDivider(line: string) {
  const values = cells(line)
  return values.length > 0 && values.every(value => /^:?-{3,}:?$/.test(value))
}

function fieldParts(text: string): { label: string; value: string } | null {
  const match = text.match(/^\*\*([^*]+?)(?::)?\*\*\s*:?\s*(.*)$/)
  if (match) return { label: match[1].replace(/:$/, '').trim(), value: match[2] || 'Not provided' }
  const plain = text.match(/^([^:]{2,60})\s*:\s+(.+)$/)
  return plain ? { label: plain[1].trim(), value: plain[2].trim() } : null
}

function decisionParts(text: string): { label: string; value: string } | null {
  const clean = text.replace(/\*\*/g, '').replace(/^[-*]\s+/, '').trim()
  const match = clean.match(/^((?:MD\s+)?(?:BID\s+)?(?:DECISION|VERDICT|RECOMMENDATION))\s*:\s*(.+)$/i)
  return match ? { label: match[1], value: match[2] } : null
}

export function MarkdownReport({ content }: MarkdownReportProps) {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []

  for (let index = 0; index < lines.length;) {
    const line = lines[index].trim()
    if (!line) {
      index += 1
      continue
    }

    if (/^(-{3,}|_{3,}|\*{3,})$/.test(line)) {
      blocks.push(<hr key={index} className="my-6 border-0 border-t border-gray-200" />)
      index += 1
      continue
    }

    if (line.startsWith('|') && index + 1 < lines.length && isDivider(lines[index + 1])) {
      const header = cells(lines[index])
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].trim().startsWith('|')) {
        if (!isDivider(lines[index])) rows.push(cells(lines[index]))
        index += 1
      }
      blocks.push(
        <div key={`table-${index}`} className="my-4 overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full min-w-[680px] border-collapse text-left text-sm">
            <thead className="bg-gray-100 text-gray-800">
              <tr>{header.map((value, i) => <th key={i} className="border-b border-r border-gray-200 px-3 py-2.5 font-semibold last:border-r-0">{inline(value)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="align-top even:bg-gray-50/60">
                  {header.map((_, cellIndex) => <td key={cellIndex} className="border-b border-r border-gray-100 px-3 py-2.5 leading-relaxed last:border-r-0">{inline(row[cellIndex] || '')}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      const className = heading[1].length === 1
        ? 'mt-5 mb-2 text-base font-bold text-gray-900'
        : 'mt-4 mb-2 font-semibold text-gray-900'
      blocks.push(<div key={index} className={className}>{inline(heading[2])}</div>)
      index += 1
      continue
    }

    const decision = decisionParts(line)
    if (decision) {
      const conditional = /conditional|watchlist|verify/i.test(decision.value)
      const negative = /no-go|drop|reject/i.test(decision.value)
      blocks.push(
        <section key={index} className="my-5 overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm">
          <div className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">{decision.label}</div>
            <div className={`inline-flex w-fit items-center rounded-md border px-3 py-1.5 text-sm font-bold ${
              negative ? 'border-red-200 bg-red-50 text-red-800' : conditional ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'
            }`}>{decision.value.replace(/[⚠️✅❌]/gu, '').trim()}</div>
          </div>
        </section>,
      )
      index += 1
      continue
    }

    const boldHeading = line.match(/^\*\*([^*]+)\*\*$/)
    if (boldHeading) {
      const isScore = /(?:SCORE|DECISION|RECOMMENDATION|VERDICT)/i.test(boldHeading[1])
      blocks.push(isScore ? (
        <div key={index} className="my-5 rounded-xl border border-orange-200 bg-orange-50 px-4 py-3 text-base font-bold text-gray-900 shadow-sm">
          {boldHeading[1]}
        </div>
      ) : (
        <h3 key={index} className="mb-3 mt-7 border-l-4 border-orange-500 pl-3 text-sm font-bold uppercase tracking-[0.08em] text-gray-900">
          {boldHeading[1]}
        </h3>
      ))
      index += 1
      continue
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ''))
        index += 1
      }
      const fields = items.map(fieldParts)
      if (fields.every(Boolean)) {
        blocks.push(
          <dl key={`fields-${index}`} className="my-4 divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            {fields.map((field, i) => field && (
              <div key={i} className="grid gap-1 px-4 py-3 sm:grid-cols-[minmax(180px,26%)_1fr] sm:gap-5 sm:px-5">
                <dt className="text-[11px] font-bold uppercase tracking-[0.08em] text-slate-500 sm:pt-0.5">{field.label}</dt>
                <dd className={`leading-relaxed ${/^not (specified|provided|verified)/i.test(field.value) ? 'font-medium text-amber-700' : 'text-slate-700'}`}>
                  {inline(field.value)}
                </dd>
              </div>
            ))}
          </dl>,
        )
      } else {
        blocks.push(<ul key={`list-${index}`} className="my-3 space-y-2 rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm">{items.map((item, i) => <li key={i} className="flex gap-3 leading-relaxed before:mt-2 before:h-1.5 before:w-1.5 before:flex-none before:rounded-full before:bg-orange-500"><span className="min-w-0">{inline(item)}</span></li>)}</ul>)
      }
      continue
    }

    if (/^\d+\.\s+/.test(line)) {
      // Keep the author's numbers: a numbered item followed by bullets starts a
      // new block, and renumbering each block from 1 would print "1, 1, 1".
      const items: { number: string; text: string }[] = []
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        const [, number, text] = lines[index].trim().match(/^(\d+)\.\s+(.*)$/) || []
        items.push({ number, text })
        index += 1
      }
      blocks.push(
        <ol key={`ordered-${index}`} className="my-4 space-y-3">
          {items.map((item, i) => (
            <li key={i} className="flex gap-3 rounded-lg border border-gray-100 bg-white px-4 py-3 leading-relaxed shadow-sm">
              <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-gray-900 text-xs font-bold text-white">{item.number}</span>
              <span className="pt-0.5">{inline(item.text)}</span>
            </li>
          ))}
        </ol>,
      )
      continue
    }

    blocks.push(<p key={index} className="my-2 leading-relaxed">{inline(line)}</p>)
    index += 1
  }

  return <div className="text-sm text-gray-700">{blocks}</div>
}
