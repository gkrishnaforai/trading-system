"""Support agents — the ops bucket, separate from the signal agents.

custodian.py is the supervisor; it coordinates three worker roles:
  sensors     deterministic detectors (job errors, stale data, db)
  diagnoser   error signature → diagnosis + remediation proposal
  remediator  risk-tiered executor — T1/T2 auto, T3 escalates
"""
