"""Metals Pulse — two-layer metals engine.

  Macro metals regime   — shared across metals: real yields, dollar,
                          liquidity, credit stress, inflation, growth.
                          Classifies the environment; never picks a metal.
  Metal opportunity     — per-metal fundamental + fear/entry scores.

Same philosophy as the equity selloff engine: fear is the entry
condition, not the thesis. A metal scores as an accumulation
candidate when structural demand remains intact while price is
discounted — and the driver that reprices it is identifiable.

Deterministic scoring only. LLM explains; never scores.
"""
