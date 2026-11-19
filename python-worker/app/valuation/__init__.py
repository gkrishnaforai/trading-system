"""Valuation composition layer — growth priced-in, decision bands.

Reads fair_value_v2_runs (the engine's journaled output: blended FV,
bear/base/bull scenarios, reverse-DCF implied growth, relative
valuation, decision scalars) and computes the *inverse* metrics the
runs don't carry: required CAGR under our exit multiple, forecast-vs-
required expectation gap, and multiple-compression drag. Read layer —
never re-runs the FV methods."""
