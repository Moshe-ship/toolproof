"""Tests for trust score module."""

from toolproof.verifier import Verdict, VerificationResult
from toolproof.trust import TrustScore, TrustReport


def _result(verdict: Verdict, tool: str = "test") -> VerificationResult:
    return VerificationResult(
        claim_tool=tool,
        claim_arguments={},
        claim_response=None,
        verdict=verdict,
    )


def test_perfect_score():
    score = TrustScore(verified=10, unverified=0, tampered=0)
    assert score.score == 1.0
    assert score.grade == "A"
    assert score.risk_level == "LOW"


def test_no_claims():
    score = TrustScore()
    assert score.score == 1.0
    assert score.total == 0


def test_mixed_score():
    score = TrustScore(verified=7, unverified=2, tampered=1)
    assert score.total == 10
    assert score.score == 0.7
    assert score.grade == "C"
    assert score.risk_level == "HIGH"


def test_all_unverified():
    score = TrustScore(verified=0, unverified=5, tampered=0)
    assert score.score == 0.0
    assert score.grade == "F"
    assert score.risk_level == "MEDIUM"


def test_all_tampered():
    score = TrustScore(verified=0, unverified=0, tampered=3)
    assert score.score == 0.0
    assert score.grade == "F"
    assert score.risk_level == "HIGH"


def test_trust_report():
    results = [
        _result(Verdict.VERIFIED, "search"),
        _result(Verdict.VERIFIED, "write"),
        _result(Verdict.TAMPERED, "delete"),
        _result(Verdict.UNVERIFIED, "execute"),
    ]
    report = TrustReport(results=results)

    assert len(report.verified) == 2
    assert len(report.tampered) == 1
    assert len(report.unverified) == 1

    score = report.trust_score
    assert score.verified == 2
    assert score.tampered == 1
    assert score.unverified == 1
    assert score.score == 0.5


def test_trust_report_serialization():
    results = [_result(Verdict.VERIFIED)]
    report = TrustReport(results=results, session_id="test-123")
    data = report.to_dict()
    assert data["session_id"] == "test-123"
    assert data["trust_score"]["verified"] == 1
    assert len(data["results"]) == 1


def test_grade_boundaries():
    assert TrustScore(verified=96, unverified=4).grade == "A"
    assert TrustScore(verified=90, unverified=10).grade == "B"
    assert TrustScore(verified=75, unverified=25).grade == "C"
    assert TrustScore(verified=55, unverified=45).grade == "D"
    assert TrustScore(verified=40, unverified=60).grade == "F"
