'use client'

import Link from 'next/link'

/** Minimal markdown renderer for post bodies — headings, bullets,
 * rules, paragraphs; **bold**, `code`, [links](/path). */

function Inline({ text }: { text: string }) {
  const out: React.ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*]+\*)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const t = m[0]
    const k = `m${i++}`
    if (t.startsWith('**')) {
      out.push(
        <strong key={k} className="font-semibold text-ink">
          {t.slice(2, -2)}
        </strong>,
      )
    } else if (t.startsWith('`')) {
      out.push(
        <code
          key={k}
          className="rounded bg-surface px-1 py-0.5 font-mono text-[0.85em] text-accent"
        >
          {t.slice(1, -1)}
        </code>,
      )
    } else if (t.startsWith('[')) {
      const mm = t.match(/\[([^\]]+)\]\(([^)]+)\)/)
      if (mm) {
        const [, label, href] = mm
        const cls = 'text-accent underline decoration-accent/30 underline-offset-2 hover:decoration-accent'
        out.push(
          href.startsWith('/') ? (
            <Link key={k} href={href} className={cls}>
              {label}
            </Link>
          ) : (
            <a key={k} href={href} className={cls}>
              {label}
            </a>
          ),
        )
      } else out.push(t)
    } else {
      out.push(<em key={k}>{t.slice(1, -1)}</em>)
    }
    last = m.index + t.length
  }
  if (last < text.length) out.push(text.slice(last))
  return <>{out}</>
}

export function Md({ source }: { source: string }) {
  const lines = (source || '').split('\n')
  const blocks: React.ReactNode[] = []
  let i = 0
  for (const line of lines) {
    const k = `l${i++}`
    const t = line.trimEnd()
    if (!t.trim()) continue
    if (t.startsWith('### ')) {
      blocks.push(
        <h3
          key={k}
          className="mt-6 mb-1.5 text-[15px] font-semibold tracking-tight text-ink"
        >
          <Inline text={t.slice(4)} />
        </h3>,
      )
    } else if (t.startsWith('## ')) {
      blocks.push(
        <h2
          key={k}
          className="mt-7 mb-2 text-[18px] font-semibold tracking-tight text-ink"
        >
          <Inline text={t.slice(3)} />
        </h2>,
      )
    } else if (t.startsWith('---')) {
      blocks.push(<hr key={k} className="my-6 border-hairline" />)
    } else if (t.startsWith('- ')) {
      blocks.push(
        <div key={k} className="flex gap-2.5 py-0.5 pl-1 text-[14.5px] leading-relaxed text-muted">
          <span className="mt-[9px] h-[3px] w-[3px] shrink-0 rounded-full bg-accent" />
          <span>
            <Inline text={t.slice(2)} />
          </span>
        </div>,
      )
    } else {
      blocks.push(
        <p
          key={k}
          className="my-2.5 text-[14.5px] leading-relaxed text-muted"
        >
          <Inline text={t} />
        </p>,
      )
    }
  }
  return <div>{blocks}</div>
}
