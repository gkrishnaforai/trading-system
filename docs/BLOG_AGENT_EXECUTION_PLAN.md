---
description: Execution Plan for Blog + Trading Plan Agents (Phase 1: B1 position-trade; Phase 2: swing; Phase 3: B2)
---

# Goal
Deliver a production-ready pipeline that generates:

- **Option A (Free)**: grounded blogs that convert.
- **Option B1 (Paid)**: actionable trading plans (position default; swing optional).

# Non-goals (for Phase 1)
- Backtesting framework
- Full portfolio-aware optimization
- Transcript-level earnings analysis

# Phase 0: Prerequisites (already in progress)
- Ensure data refresh UI supports `consensus_data` and `price_targets`.
- Ensure fair_value_v2 works against current DB schemas.

# Phase 1: Run UX foundation (Streamlit)
Outcome: operator can reliably find, load, and interpret run results.

- Add portfolio run history to `Trading_Decision_V3_Portfolio` page
- Add run picker and run-type grouping
- Improve run result rendering for refresh vs trading_decision_v3

Definition of done
- From a portfolio, you can select a run from the last N runs without copy/paste.
- The page shows run status, operation, symbols count, and a clean results table.

# Phase 2: Research Pack service
Outcome: build a reusable structured snapshot for each symbol.

Deliverables
- A `research_pack` builder that:
  - fetches latest price/indicators
  - fetches earnings date (if available)
  - fetches top news and clusters duplicates
  - fetches analyst consensus/targets and ratings summary
  - fetches fair value v1 + v2 outputs
  - produces citations
- Persist packs for auditing and regeneration.

Definition of done
- You can generate and store a pack for any symbol in the watchlist/portfolio.
- Pack includes timestamps and freshness warnings.

# Phase 3: B1 Plan Builder (position profile)
Outcome: deterministic plan object with entry/risk/targets.

Deliverables
- Plan builder produces `trade_plan.profiles.position`.
- Enforces locked rules:
  - earnings window block (7 days)
  - missing earnings date warning
  - no-trim-on-RSI-alone

Definition of done
- Given a research pack, it outputs a complete position plan.
- Verifier can confirm required fields present and all numbers are sourced.

# Phase 4: Free + Paid writers
Outcome: two publishable articles from the same research pack.

Deliverables
- Free writer (Option A): commentary + debate + CTA + plan preview with locked levels.
- Paid writer (Option B1): full plan with exact levels and ladder.
- Redaction/verifier:
  - ensures free does not leak paid-only fields
  - ensures paid contains required sections

Definition of done
- For a symbol, the system produces both free and paid outputs with consistent tone and structure.

# Phase 5: Add swing profile
Outcome: same pipeline, second execution profile.

Deliverables
- Plan builder produces `trade_plan.profiles.swing`.
- UI toggle between position and swing in paid view.

Definition of done
- Both plans exist, differ meaningfully, and obey gating rules.

# Phase 6: Upgrade path to B2
Outcome: add fundamentals + valuation memo modules.

Deliverables
- B2 writer template attaches:
  - fundamental thesis
  - valuation scenario table

Definition of done
- B2 can be generated without changing research pack or plan builder.

# Telemetry and quality gates
Track per-article:
- data freshness
- citations count
- verifier pass/fail
- free->paid clicks
- paid conversion (if available)
