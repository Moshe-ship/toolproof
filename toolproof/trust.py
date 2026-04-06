"""Trust score calculation and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from toolproof.verifier import Verdict, VerificationResult


@dataclass
class TrustScore:
    """Aggregated trust score from verification results."""

    verified: int = 0
    unverified: int = 0
    tampered: int = 0

    @property
    def total(self) -> int:
        return self.verified + self.unverified + self.tampered

    @property
    def score(self) -> float:
        """Trust score from 0.0 to 1.0."""
        if self.total == 0:
            return 1.0  # No claims = nothing to distrust
        return self.verified / self.total

    @property
    def score_percent(self) -> float:
        return self.score * 100

    @property
    def grade(self) -> str:
        """Human-readable grade."""
        s = self.score_percent
        if s >= 95:
            return "A"
        if s >= 85:
            return "B"
        if s >= 70:
            return "C"
        if s >= 50:
            return "D"
        return "F"

    @property
    def risk_level(self) -> str:
        if self.tampered > 0:
            return "HIGH"
        if self.unverified > 0:
            return "MEDIUM"
        return "LOW"

    def to_dict(self) -> dict:
        return {
            "verified": self.verified,
            "unverified": self.unverified,
            "tampered": self.tampered,
            "total": self.total,
            "score": round(self.score, 4),
            "score_percent": round(self.score_percent, 1),
            "grade": self.grade,
            "risk_level": self.risk_level,
        }


@dataclass
class TrustReport:
    """Full trust report for a verification session."""

    results: list[VerificationResult] = field(default_factory=list)
    session_id: Optional[str] = None

    @property
    def trust_score(self) -> TrustScore:
        score = TrustScore()
        for r in self.results:
            if r.verdict == Verdict.VERIFIED:
                score.verified += 1
            elif r.verdict == Verdict.UNVERIFIED:
                score.unverified += 1
            elif r.verdict == Verdict.TAMPERED:
                score.tampered += 1
        return score

    @property
    def verified(self) -> list[VerificationResult]:
        return [r for r in self.results if r.verdict == Verdict.VERIFIED]

    @property
    def unverified(self) -> list[VerificationResult]:
        return [r for r in self.results if r.verdict == Verdict.UNVERIFIED]

    @property
    def tampered(self) -> list[VerificationResult]:
        return [r for r in self.results if r.verdict == Verdict.TAMPERED]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "trust_score": self.trust_score.to_dict(),
            "results": [r.to_dict() for r in self.results],
        }
