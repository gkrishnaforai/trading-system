"""Portfolio strategy — the top-down allocation layer.

Daily Board picks names; this engine answers the question above it:
how much of each THEME should the book hold, given the market regime,
where capital is rotating, what events could flip the tape, and how
much earnings exposure the book carries into each week.

Deterministic scoring, journaled daily (strategy_snapshots), advisory
only — it produces target weights and reasons, never orders.
"""
