import Link from 'next/link'

type Vol = { vix?: number | null; vxn?: number | null; vxn_chg_5d?: number | null }

function vixTone(v?: number | null) {
  // VIX bands: <15 calm · <20 normal · <28 elevated · ≥28 high fear
  if (v == null) return 'text-muted'
  if (v < 15) return 'text-aggressive'
  if (v < 20) return 'text-muted'
  if (v < 28) return 'text-caution'
  return 'text-defensive'
}

function vxnTone(v?: number | null) {
  // VXN runs ~1.3x VIX — bands from the regime engine's own levels
  if (v == null) return 'text-muted'
  if (v < 20) return 'text-aggressive'
  if (v < 28) return 'text-muted'
  if (v < 35) return 'text-caution'
  return 'text-defensive'
}

/** Fear-gauge chips: VIX + VXN + the contrarian directive
 *  (fear posture → be greedy selectively; greed → be fearful). */
export function VolChips({
  vol, bias,
}: {
  vol?: Vol | null
  bias?: string | null
}) {
  if (!vol && !bias) return null
  const vix = vol?.vix
  const vxn = vol?.vxn
  const chg = vol?.vxn_chg_5d
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {vix != null && (
        <span className={`inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 font-mono ${vixTone(vix)}`}>
          VIX {vix.toFixed(1)}
        </span>
      )}
      {vxn != null && (
        <span className={`inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 font-mono ${vxnTone(vxn)}`}>
          VXN {vxn.toFixed(1)}
          {chg != null && (
            <span className={chg > 0 ? 'text-defensive' : 'text-aggressive'}>
              {chg > 0 ? '+' : ''}{chg.toFixed(1)}/5d
            </span>
          )}
        </span>
      )}
      {bias === 'fear' && (
        <Link href="/plan"
          className="inline-flex items-center gap-1.5 rounded-full border border-aggressive/40 px-2.5 py-1 text-aggressive hover:bg-aggressive/10">
          ↯ be greedy — selectively → plan
        </Link>
      )}
      {bias === 'greed' && (
        <Link href="/plan"
          className="inline-flex items-center gap-1.5 rounded-full border border-caution/40 px-2.5 py-1 text-caution hover:bg-caution/10">
          ☂ be fearful — hedges cheap → plan
        </Link>
      )}
    </div>
  )
}
