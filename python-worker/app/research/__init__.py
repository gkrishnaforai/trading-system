"""Research engine — evidence-driven, deterministic-first.

Layered contract (same as every engine in this repo):
    deterministic evidence → bounded LLM interpretation →
    journaled scores → human decision
Nothing here places orders. The LLM extracts/classifies/challenges
against evidence; it never assigns scores or overrides gates.
"""
