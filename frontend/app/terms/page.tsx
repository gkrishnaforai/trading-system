export const dynamic = 'force-static'

const VERSION = '2025-11-01'

function Section({
  id, title, children,
}: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="pt-10">
      <h2 className="text-[13px] font-semibold tracking-[0.14em] uppercase text-ink">
        {title}
      </h2>
      <div className="pt-3 space-y-3 text-[13px] leading-relaxed text-muted">
        {children}
      </div>
    </section>
  )
}

const TOC = [
  ['terms', 'Terms of Use'],
  ['educational', 'Educational Purpose — No Investment Advice'],
  ['risk', 'Investment Risk Disclosure'],
  ['ai', 'AI-Generated Analysis'],
  ['portfolio', 'Portfolio Tools'],
  ['rankings', 'Rankings, Screens & Independence'],
  ['affiliate', 'Affiliate & Advertising Disclosure'],
  ['sponsored', 'Sponsored Content & Paid Promotion'],
  ['alerts', 'Alerts'],
  ['data', 'Market Data'],
  ['privacy', 'Privacy (summary)'],
  ['regulatory', 'Regulatory Status'],
  ['contact', 'Contact'],
] as const

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-5 pb-24">
      <header className="pt-8 pb-6">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Legal
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          Terms &amp; <span className="text-accent">disclosures</span>
        </h1>
        <p className="pt-3 max-w-xl text-[13px] leading-relaxed text-muted">
          Osprey Desk is an independent financial research and education
          platform. Please read these terms carefully — they describe what
          the service is, what it is not, and the risks you accept by
          using it.
        </p>
        <p className="pt-2 font-mono text-[11px] text-faint">
          version {VERSION}
        </p>
      </header>

      <nav className="rounded-xl border border-hairline bg-card px-5 py-4">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Contents
        </div>
        <ol className="pt-3 grid gap-x-8 gap-y-1.5 text-[13px] sm:grid-cols-2">
          {TOC.map(([id, label], i) => (
            <li key={id}>
              <a href={`#${id}`} className="text-muted hover:text-accent">
                {i + 1}. {label}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <Section id="terms" title="1. Terms of Use">
        <p>
          By accessing or using Osprey Desk (&quot;the Service&quot;), you
          agree to these Terms of Use. If you do not agree, do not use the
          Service.
        </p>
        <p>
          The Service provides financial research tools: company profiles,
          SEC filing and earnings information, market news, fundamental
          and technical indicators, stock screening, user-configured
          alerts, and user-controlled portfolio tracking and analytics.
        </p>
        <p>
          You must provide accurate account information and keep your
          credentials confidential. You are responsible for activity under
          your account. We may suspend accounts that misuse the Service,
          attempt unauthorized access, or scrape or redistribute content
          in violation of these terms.
        </p>
        <p>
          The Service is provided &quot;as is&quot; and &quot;as
          available&quot; without warranties of any kind, express or
          implied, including accuracy, completeness, timeliness,
          merchantability, or fitness for a particular purpose. To the
          maximum extent permitted by law, we are not liable for any
          investment losses, lost profits, or other damages arising from
          use of or reliance on the Service.
        </p>
        <p>
          We may update these terms; continued use after an update
          constitutes acceptance. The current version is always posted at
          this page.
        </p>
      </Section>

      <Section id="educational" title="2. Educational Purpose — No Investment Advice">
        <p>
          <span className="text-ink font-medium">
            Osprey Desk is a research and education platform. Nothing on
            the Service is investment advice, a recommendation, or an
            offer or solicitation to buy or sell any security.
          </span>
        </p>
        <p>
          All content — analysis, screens, rankings, scores, regime
          classifications, AI-generated research, and portfolio metrics —
          is general, impersonal information intended to help you conduct
          your own research. It is not tailored to your individual
          financial situation, objectives, or risk tolerance, and it must
          not be treated as such.
        </p>
        <p>
          No adviser–client, broker–client, or fiduciary relationship is
          created by your use of the Service. Investment decisions are
          solely yours. You should independently verify any information
          and consult a licensed financial adviser, tax professional, or
          attorney before making investment decisions.
        </p>
      </Section>

      <Section id="risk" title="3. Investment Risk Disclosure">
        <p>
          Investing in securities involves substantial risk, including the
          possible loss of principal. Prices can move rapidly and
          unpredictably. Past performance — including any backtested,
          modeled, or historical analysis shown by the Service —{' '}
          <span className="text-ink font-medium">
            does not guarantee future results
          </span>
          .
        </p>
        <p>
          Leveraged, inverse, small-cap, and thinly traded instruments
          carry elevated risk, including the risk of losing more than your
          initial investment. Any leverage, short, or hedge discussion on
          the Service is educational analysis, not a recommendation.
        </p>
      </Section>

      <Section id="ai" title="4. AI-Generated Analysis">
        <p>
          Portions of the Service use automated and AI-generated analysis
          (verdicts, summaries, classifications, and research notes). This
          content may be incomplete, reflect stale inputs, or contain
          errors. AI output on the Service:
        </p>
        <ul className="list-disc pl-5 space-y-1.5">
          <li>separates reported facts from interpretation where shown;</li>
          <li>carries the data timestamp it was generated from;</li>
          <li>is not a prediction, price target, or guaranteed outcome;</li>
          <li>should be independently verified against primary sources
            (SEC filings, exchange data) before reliance.</li>
        </ul>
        <p>
          AI-generated content is impersonal analysis — it is not produced
          from, or tailored to, your personal circumstances.
        </p>
      </Section>

      <Section id="portfolio" title="5. Portfolio Tools">
        <p>
          Portfolio features are{' '}
          <span className="text-ink font-medium">
            user-directed tracking and calculation tools
          </span>
          . You decide which holdings to enter, in what quantities, and at
          what cost basis. The Service computes descriptive analytics —
          allocation, sector exposure, concentration, historical
          performance, volatility, and drawdown — from what you enter and
          from market data.
        </p>
        <p>
          These metrics are educational calculations, not instructions.
          The Service does not select securities for you, does not decide
          what you should buy, sell, or hold, does not manage or rebalance
          your holdings, and never takes custody of assets or executes
          transactions.
        </p>
      </Section>

      <Section id="rankings" title="6. Rankings, Screens & Independence">
        <p>
          Stock screens, rankings, scores, and readiness lists are
          generated by published, deterministic methodology applied to
          market and fundamental data. They are research outputs — not
          endorsements and not personalized recommendations.
        </p>
        <p>
          <span className="text-ink font-medium">
            Advertising revenue and affiliate compensation never
            influence analytical scores, screen membership, rankings, or
            AI verdicts.
          </span>{' '}
          Paid placements are architecturally separate from the analysis
          engine, are labeled as such, and cannot purchase favorable
          coverage.
        </p>
      </Section>

      <Section id="affiliate" title="7. Affiliate & Advertising Disclosure">
        <p>
          The Service is advertising-supported. We may receive
          compensation when you click certain links, sign up for products
          or services, or open accounts through links on the platform.
          This is a material connection, and we disclose it plainly:
        </p>
        <ul className="list-disc pl-5 space-y-1.5">
          <li>paid placements are labeled &quot;Sponsored&quot; or
            &quot;Advertisement&quot; adjacent to the content or link;</li>
          <li>affiliate links carry a disclosure near the link itself —
            not only in a footer or this document;</li>
          <li>compensation may influence which advertisements or partner
            links appear and their placement — but never analysis,
            scores, or rankings;</li>
          <li>review each product&apos;s own terms, fees, and risks before
            deciding; we do not endorse every advertiser.</li>
        </ul>
        <p className="rounded-lg border border-hairline bg-card px-4 py-3">
          <span className="font-medium text-ink">Affiliate Disclosure:</span>{' '}
          We may receive compensation when you click certain links or sign
          up for products and services through our platform. Our financial
          analysis and ranking methodology are maintained separately from
          paid placements. Please review the relevant product&apos;s
          terms, fees, and risks before making a decision.
        </p>
      </Section>

      <Section id="sponsored" title="8. Sponsored Content & Paid Promotion">
        <p>
          If we ever publish content paid for by a sponsor — including any
          paid promotion of a security — it will be labeled{' '}
          <span className="text-ink font-medium">
            &quot;SPONSORED CONTENT — PAID PROMOTION&quot;
          </span>{' '}
          with the sponsor identified and the fact of compensation
          disclosed at the placement itself, consistent with the
          disclosure expectations of FTC guidance and Section 17(b) of the
          Securities Act.
        </p>
        <p>
          Sponsored material is promotional content, not independent
          research. No advertiser may purchase undisclosed stock rankings
          or positive financial analysis on the Service.
        </p>
      </Section>

      <Section id="alerts" title="9. Alerts">
        <p>
          Price, earnings, filing, and news alerts are{' '}
          <span className="text-ink font-medium">
            informational notifications configured by you
          </span>
          . An alert tells you something happened; it never tells you what
          to do about it. Delivery may be delayed or fail; alerts are a
          convenience, not a guarantee of timely notice, and should not be
          your sole monitoring mechanism.
        </p>
      </Section>

      <Section id="data" title="10. Market Data">
        <p>
          Market data, prices, fundamentals, and filings come from
          third-party providers and public sources. Data may be delayed,
          incomplete, or contain errors, and is subject to provider and
          exchange licensing terms — it is for your personal, internal use
          and may not be redistributed.
        </p>
        <p>
          Figures shown on the Service can disagree with your broker or
          other sources; your broker&apos;s statements and official
          filings are authoritative for your accounts.
        </p>
      </Section>

      <Section id="privacy" title="11. Privacy (summary)">
        <p>
          We collect the account information you provide (name, email,
          password — stored only as a hash), your portfolio entries, and
          technical/usage data needed to operate and secure the Service
          (including sign-in and action audit logs). We do not sell your
          personal information. A full Privacy Policy will be published
          here before public launch; until then this summary governs our
          handling.
        </p>
      </Section>

      <Section id="regulatory" title="12. Regulatory Status">
        <p>
          Osprey Desk is{' '}
          <span className="text-ink font-medium">
            not registered as an investment adviser or broker-dealer
          </span>{' '}
          with the SEC or any state regulator. We do not provide
          personalized investment advice, manage assets, solicit or
          effect securities transactions, or receive transaction-based
          compensation.
        </p>
        <p>
          Nothing on the Service constitutes an offer to sell or a
          solicitation of an offer to buy any security. If any part of the
          Service is ever found to require registration or licensing,
          that functionality will be suspended until compliant — a
          disclaimer is not a substitute for registration.
        </p>
      </Section>

      <Section id="contact" title="13. Contact">
        <p>
          Questions about these terms or a disclosure concern: contact
          the operator through the channels listed on the platform.
          Material changes to these terms are posted here with an updated
          version date.
        </p>
      </Section>
    </main>
  )
}
