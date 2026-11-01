"""Theme Intelligence — rank themes by expected 6-12m opportunity
and maintain quality-weighted theme indices.

  Theme Opportunity Score   does this theme deserve capital NOW —
                            macro alignment, earnings/revisions,
                            valuation, demand, momentum, resilience.
  Scenario engine           12-month macro scenario probabilities ×
                            per-theme sensitivity → expected,
                            downside, robustness.
  Index builder             constituent scores → capped weights;
                            pure + quality versions. The index
                            measures the theme; the portfolio layer
                            selects from it — kept separate.

Distinct from the index's job: a theme can perform well while being
a poor place for new capital, and vice versa — the score prices
expected opportunity, the index prices realized performance.

Deterministic scoring only; every leg is journaled evidence.
"""
