---
description: Blog + Trading Plan Agent Design (Free A / Paid B1; position-trade default with swing option)
---

# Scope
This document defines the architecture and product behavior for generating:

- **Option A (Free)**: credible market commentary that motivates users to upgrade.
- **Option B1 (Paid)**: actionable trading plans (position-trade default) with an optional swing profile.

The system is designed so **B2 (paid investment memo)** can be added later without refactoring the pipeline.

# Product tiers

## Option A (Free)
Goal: build trust, educate, and create curiosity.

- Must be useful and grounded.
- Must not include paid-only specifics.
- Must include a structured preview of what paid unlocks.

### Free content must include
- Hook (what changed + why it matters)
- Facts panel (price move, trend regime, key events)
- News/catalyst summary (cited)
- Bull vs bear debate (balanced)
- CTA block to unlock the plan

### Free content must not include
- Numeric entry zones / exact levels
- Numeric invalidation level
- Full target ladder values
- Explicit position sizing directives
- Full fair value breakdown table

## Option B1 (Paid)
Goal: specific and actionable.

- Must produce a concrete plan using stable action vocabulary.
- Must include numeric entry/risk/targets.
- Must include warnings and gating rules.

### Paid trading plan must include
- Trade card: action, setup type, horizon, conviction
- Entry plan: triggers + zone + confirmations
- Risk plan: invalidation level + reason + what to do if invalidated
- Target ladder: staged exits and trim rules
- Catalyst calendar: upcoming known events and how they affect the plan
- Evidence block: key indicators/facts + citations

# Shared architecture

## Research Pack (single source of truth)
A single structured payload per symbol and as-of timestamp.

Recommended top-level fields:

- `market`: price, returns, volatility/ATR (if available)
- `technicals`: EMA20/SMA50/SMA200, RSI/MACD, regime tags, candidate support/resistance
- `events`: next earnings date, corporate actions
- `news`: top-K items with dedup clusters
- `analyst`: ratings summary, consensus target/high/low, analyst count, last update
- `fundamentals`: minimal snapshot (growth, margins, leverage) for context
- `valuation`: FV v1 + FV v2 results + feature-quality flags
- `citations`: per-fact source refs

The Research Pack is persisted (JSON) so drafts are reproducible and auditable.

## Citation model
Every numeric or time-sensitive claim should map to a citation:

- `source_type`: `db_table` | `news_item` | `computed`
- `source_ref`: table/key/as_of_ts, or news id

# Execution profiles (B1)
B1 provides two plan profiles derived from the same Research Pack:

- `position` (default)
- `swing` (optional)

Both share schema; only thresholds/levels and pacing differ.

## Shared plan schema

```
trade_plan:
  symbol: str
  as_of_ts: str
  profiles:
    position:
      action: add|hold|trim|reduce|sell|no_trade
      setup_type: pullback|breakout|base_break|reversal|mean_reversion
      timeline_days: [min,max]
      entry:
        type: pullback|breakout|...
        zone: [ ... ]
        confirmation: [ ... ]
      risk:
        invalid_level: number
        reason: str
      targets:
        - name: str
          level: number
          rule: str
      gate:
        blocked: bool
        rule: str
        window_days: int
        earnings_date: str|null
        days_to_earnings: int|null
        warning: str|null
      warnings: [str]
      citations: {...}
    swing: { same schema }
```

# Locked policy rules

## Earnings window gating
- **Block new entries** within **7 calendar days** of earnings when earnings date is known.
- Allowed actions during block: hold/reduce/trim/sell/no_trade.
- If the system would otherwise add, convert to hold with a note: defer add until after event + confirmation.

### Missing earnings date
- Allow entries but add a prominent warning: "earnings date unavailable".
- Recommended risk mitigation: suggest reduced initial size until calendar confirmed.

## Trim rule
Never trim on RSI alone. Trim only when RSI extreme AND additional exhaustion/extension evidence is present.

# Free -> Paid conversion pattern
Free post includes a "Plan Preview" with locked values:

- Entry: "Pullback to EMA20 / SMA50 (levels locked)"
- Invalidation: "Below SMA50 (level locked)"
- Targets: "Prior high → extension (levels locked)"

Paid unlocks the exact levels and complete ladder.

# Extensibility to B2
B2 is added by attaching two modules to the same Research Pack:

- `fundamental_thesis` (moat, growth durability, capital allocation)
- `valuation_scenarios` (FV scenario table, sensitivity)

No changes required to selection, retrieval, or gating.
