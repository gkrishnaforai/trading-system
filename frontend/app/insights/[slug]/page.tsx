import Link from 'next/link'
import { notFound } from 'next/navigation'
import { api } from '@/lib/api'
import { Md } from '@/components/markdown'

export const dynamic = 'force-dynamic'

export default async function PostPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const post = await api.post(slug)
  if (!post) notFound()
  return (
    <main className="mx-auto max-w-3xl px-5 pb-20 pt-10">
      <Link
        href="/insights"
        className="text-[12px] font-medium text-faint hover:text-accent"
      >
        ← insights
      </Link>
      <div className="mt-5 flex items-center gap-2.5">
        <span className="rounded-full border border-accent/40 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider text-accent">
          {(post.kind ?? 'post').replace('_', ' ')}
        </span>
        <span className="font-mono text-[11.5px] text-faint">
          {post.as_of}
        </span>
      </div>
      <h1 className="mt-3 text-display font-semibold tracking-tight text-ink">
        {post.title}
      </h1>
      {post.dek && (
        <p className="mt-3 border-l-2 border-accent/60 pl-3.5 text-[14.5px] leading-relaxed text-muted">
          {post.dek}
        </p>
      )}
      {post.symbols && post.symbols.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {post.symbols.map((s) => (
            <Link
              key={s}
              href={`/stock?sym=${s}`}
              className="rounded border border-hairline px-1.5 py-0.5 font-mono text-[11px] text-muted hover:border-accent/50 hover:text-accent"
            >
              {s}
            </Link>
          ))}
        </div>
      )}
      <article className="mt-8">
        <Md source={post.body_md ?? ''} />
      </article>
      <p className="mt-12 border-t border-hairline pt-5 text-[12px] text-faint">
        Generated from journaled evidence on{' '}
        {post.published_at?.slice(0, 10) ?? post.as_of}. Advisory only —
        deterministic reads, human decides.
      </p>
    </main>
  )
}
