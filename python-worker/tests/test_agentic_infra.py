"""agentic_infra — seed priors + journaled-evidence scoring.

Contracts under test:
- seeds classify role/monetization/sublayers (priors, flagged)
- consumption beats seat on the monetization leg — agents buy usage
- unknown growth is excluded with coverage reported, never zeroed
- candidates can never tier above 'candidate' — review gate
- status upgrades seeded → evidence_backed only on real evidence rows
"""
from unittest.mock import patch

from app.signals import agentic_infra as ai


def _ctx(sym="TEST", role="core", monetization="consumption",
         sublayers_n=2, evidence_n=0, rev_growth=0.2):
    return {"symbol": sym, "role": role, "monetization": monetization,
            "sublayers_n": sublayers_n, "evidence_n": evidence_n,
            "rev_growth": rev_growth, "est_revision_pct": None}


def test_core_consumption_scores_top():
    out = ai._score(_ctx())
    # role 85, sublayer 70, monet 85, growth 70, evidence 30 → ~67
    assert out["ais"] > 60
    assert out["components"]["monetization_fit"]["score"] == 85


def test_seat_monetization_penalized():
    cons = ai._score(_ctx(monetization="consumption"))
    seat = ai._score(_ctx(monetization="seat"))
    assert cons["components"]["monetization_fit"]["score"] > \
        seat["components"]["monetization_fit"]["score"]
    assert cons["ais"] > seat["ais"]


def test_unknown_growth_excluded_not_zeroed():
    out = ai._score(_ctx(rev_growth=None))
    assert out["components"]["growth_durability"]["unknown"]
    # renormalized over remaining legs — not dragged to zero
    assert out["ais"] > 40
    assert out["coverage_pct"] < 1.0


def test_no_evidence_is_seed_prior_not_zero():
    out = ai._score(_ctx(evidence_n=0))
    assert out["components"]["ai_evidence"]["score"] == 30
    assert "unverified" in out["components"]["ai_evidence"]["note"]


def test_candidate_capped_at_candidate_tier():
    # a candidate with perfect numbers still can't tier up
    out = ai._score(_ctx(role="candidate", sublayers_n=3,
                         evidence_n=5, rev_growth=0.4))
    assert out["tier"] == "candidate"


def test_core_name_tiers_correctly():
    strong = ai._score(_ctx(evidence_n=5, rev_growth=0.4,
                            sublayers_n=3))
    weak = ai._score(_ctx(role="watch", evidence_n=0,
                          rev_growth=-0.02, monetization="seat"))
    assert strong["tier"] == "core_infrastructure"
    assert strong["ais"] > weak["ais"]


def test_status_transitions_on_evidence():
    with patch.object(ai, "universe",
                      return_value={"XXX": {"role": "core",
                                            "sublayers": ["streaming"],
                                            "monetization": "consumption",
                                            "note": "t"}}), \
         patch.object(ai, "_ctx",
                      return_value=_ctx(sym="XXX", evidence_n=0)):
        r = ai.evaluate_symbol("xxx")
        assert r["status"] == "seeded"
        assert "seed_only" in r["flags"]
    with patch.object(ai, "universe",
                      return_value={"XXX": {"role": "core",
                                            "sublayers": ["streaming"],
                                            "monetization": "consumption",
                                            "note": "t"}}), \
         patch.object(ai, "_ctx",
                      return_value=_ctx(sym="XXX", evidence_n=3)):
        r = ai.evaluate_symbol("XXX")
        assert r["status"] == "evidence_backed"


def test_seeded_universe_names_resolve():
    seeds = ai.seeds()
    for s in ("SNOW", "MDB", "NET", "CFLT", "ORCL", "ESTC"):
        assert s in seeds, s
    assert seeds["CFLT"]["sublayers"] == ["streaming"]
    assert seeds["NET"]["monetization"] == "consumption"
