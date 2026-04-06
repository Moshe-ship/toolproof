"""Trust analytics — pattern detection from receipt history.

Analyzes receipts over time to find:
- Which tools get hallucinated most
- Which models produce lowest trust
- Cost hotspots (broken caching, expensive calls)
- Failure patterns by time of day, session, source

This is the "Karpathy eval" for tool calling:
Measure everything. Find patterns. Improve systematically.

Usage:
    from toolproof.analytics import Analyzer

    analyzer = Analyzer(store)
    report = analyzer.full_report()
    print(report.worst_tools)
    print(report.cost_hotspots)
    print(report.recommendations)
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from toolproof.receipt import Receipt, ReceiptStore


@dataclass
class ToolStats:
    """Statistics for a single tool."""

    name: str
    total_calls: int = 0
    errors: int = 0
    total_cost: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_duration_ms: float = 0.0
    sources: list[str] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        return self.errors / self.total_calls if self.total_calls > 0 else 0.0

    @property
    def avg_cost(self) -> float:
        return self.total_cost / self.total_calls if self.total_calls > 0 else 0.0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.total_calls if self.total_calls > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "total_calls": self.total_calls,
            "errors": self.errors,
            "error_rate": round(self.error_rate, 4),
            "total_cost": round(self.total_cost, 6),
            "avg_cost": round(self.avg_cost, 6),
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "avg_duration_ms": round(self.avg_duration_ms, 1),
        }


@dataclass
class CostAnomaly:
    """A cost anomaly — a call that costs significantly more than average."""

    receipt_id: str
    tool_name: str
    cost_usd: float
    avg_cost: float
    multiplier: float  # how many times more expensive than average
    tokens_in: int = 0
    cache_read: int = 0
    possible_cause: str = ""

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "tool_name": self.tool_name,
            "cost_usd": round(self.cost_usd, 6),
            "avg_cost": round(self.avg_cost, 6),
            "multiplier": round(self.multiplier, 1),
            "possible_cause": self.possible_cause,
        }


@dataclass
class AnalyticsReport:
    """Full analytics report."""

    total_receipts: int = 0
    total_cost: float = 0.0
    total_errors: int = 0
    trust_score: float = 1.0
    tool_stats: list[ToolStats] = field(default_factory=list)
    worst_tools: list[ToolStats] = field(default_factory=list)
    cost_hotspots: list[ToolStats] = field(default_factory=list)
    cost_anomalies: list[CostAnomaly] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    cache_efficiency: float = 0.0  # ratio of cache_read to tokens_in
    by_source: dict[str, int] = field(default_factory=dict)
    by_session: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_receipts": self.total_receipts,
            "total_cost": round(self.total_cost, 6),
            "total_errors": self.total_errors,
            "trust_score": round(self.trust_score, 4),
            "cache_efficiency": round(self.cache_efficiency, 4),
            "worst_tools": [t.to_dict() for t in self.worst_tools],
            "cost_hotspots": [t.to_dict() for t in self.cost_hotspots],
            "cost_anomalies": [a.to_dict() for a in self.cost_anomalies],
            "recommendations": self.recommendations,
            "by_source": self.by_source,
        }


class Analyzer:
    """Analyze receipt history for patterns and optimization opportunities."""

    def __init__(self, store: ReceiptStore):
        self.store = store

    def full_report(self) -> AnalyticsReport:
        """Generate a complete analytics report."""
        receipts = self.store.all()
        report = AnalyticsReport()

        if not receipts:
            report.recommendations.append("No receipts recorded yet. Run an agent with ToolProof first.")
            return report

        report.total_receipts = len(receipts)
        report.total_errors = sum(1 for r in receipts if r.error)
        report.total_cost = sum(r.cost_usd for r in receipts)
        clean = report.total_receipts - report.total_errors
        report.trust_score = clean / report.total_receipts

        # Tool-level stats
        report.tool_stats = self._compute_tool_stats(receipts)

        # Worst tools (highest error rate, min 3 calls)
        report.worst_tools = sorted(
            [t for t in report.tool_stats if t.total_calls >= 3],
            key=lambda t: t.error_rate,
            reverse=True,
        )[:5]

        # Cost hotspots (most expensive tools)
        report.cost_hotspots = sorted(
            report.tool_stats,
            key=lambda t: t.total_cost,
            reverse=True,
        )[:5]

        # Cost anomalies (individual calls that cost way more than average)
        report.cost_anomalies = self._find_cost_anomalies(receipts, report.tool_stats)

        # Cache efficiency
        total_tokens_in = sum(r.tokens_in for r in receipts)
        total_cache_read = sum(r.cache_read for r in receipts)
        if total_tokens_in > 0:
            report.cache_efficiency = total_cache_read / (total_tokens_in + total_cache_read)

        # By source
        for r in receipts:
            src = r.source or "unknown"
            report.by_source[src] = report.by_source.get(src, 0) + 1

        # By session
        for r in receipts:
            sid = r.session_id or "default"
            report.by_session[sid] = report.by_session.get(sid, 0) + 1

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report, receipts)

        return report

    def _compute_tool_stats(self, receipts: list[Receipt]) -> list[ToolStats]:
        """Compute per-tool statistics."""
        by_tool: dict[str, ToolStats] = {}
        for r in receipts:
            if r.tool_name not in by_tool:
                by_tool[r.tool_name] = ToolStats(name=r.tool_name)
            ts = by_tool[r.tool_name]
            ts.total_calls += 1
            if r.error:
                ts.errors += 1
            ts.total_cost += r.cost_usd
            ts.total_tokens_in += r.tokens_in
            ts.total_tokens_out += r.tokens_out
            ts.total_duration_ms += r.duration_ms
            if r.source and r.source not in ts.sources:
                ts.sources.append(r.source)

        return sorted(by_tool.values(), key=lambda t: t.total_calls, reverse=True)

    def _find_cost_anomalies(
        self,
        receipts: list[Receipt],
        tool_stats: list[ToolStats],
    ) -> list[CostAnomaly]:
        """Find individual calls that cost significantly more than average."""
        avg_by_tool = {ts.name: ts.avg_cost for ts in tool_stats}
        anomalies = []

        for r in receipts:
            if r.cost_usd <= 0:
                continue
            avg = avg_by_tool.get(r.tool_name, 0)
            if avg <= 0:
                continue
            multiplier = r.cost_usd / avg
            if multiplier >= 5.0:  # 5x or more than average
                cause = ""
                if r.cache_read == 0 and r.tokens_in > 1000:
                    cause = "Possible broken cache — zero cache_read with high tokens_in"
                elif r.tokens_in > 50000:
                    cause = "Very large input — check if context is being reprocessed"
                elif r.tokens_out > 10000:
                    cause = "Very large output — consider truncating tool responses"

                anomalies.append(CostAnomaly(
                    receipt_id=r.id,
                    tool_name=r.tool_name,
                    cost_usd=r.cost_usd,
                    avg_cost=avg,
                    multiplier=multiplier,
                    tokens_in=r.tokens_in,
                    cache_read=r.cache_read,
                    possible_cause=cause,
                ))

        return sorted(anomalies, key=lambda a: a.multiplier, reverse=True)[:10]

    def _generate_recommendations(
        self,
        report: AnalyticsReport,
        receipts: list[Receipt],
    ) -> list[str]:
        """Generate actionable recommendations based on patterns."""
        recs = []

        # Trust score
        if report.trust_score < 0.7:
            recs.append(
                f"Trust score is {report.trust_score:.0%} (Grade F/D). "
                "Consider switching to a more capable model or adding explicit "
                "tool-use instructions to the system prompt."
            )
        elif report.trust_score < 0.9:
            recs.append(
                f"Trust score is {report.trust_score:.0%}. "
                "Review the worst-performing tools below for patterns."
            )

        # Worst tools
        for t in report.worst_tools[:3]:
            if t.error_rate > 0.3:
                recs.append(
                    f"Tool '{t.name}' has {t.error_rate:.0%} error rate "
                    f"({t.errors}/{t.total_calls}). "
                    "Check if the tool definition is clear enough for the model."
                )

        # Cost anomalies
        if report.cost_anomalies:
            worst = report.cost_anomalies[0]
            recs.append(
                f"Cost anomaly: '{worst.tool_name}' call cost ${worst.cost_usd:.4f} "
                f"({worst.multiplier:.0f}x average). {worst.possible_cause}"
            )

        # Cache efficiency
        if report.cache_efficiency < 0.1 and report.total_cost > 0.10:
            recs.append(
                f"Cache efficiency is only {report.cache_efficiency:.0%}. "
                "Prompt caching may be broken. Check if tool definitions are "
                "being included in the cacheable prefix."
            )

        # High cost
        if report.total_cost > 1.0:
            recs.append(
                f"Total spend is ${report.total_cost:.2f}. "
                "Consider setting per-call and session cost limits via policy.json."
            )

        # Model diversity (check if multiple sources)
        if len(report.by_source) > 1:
            best_source = min(
                report.by_source.items(),
                key=lambda x: sum(1 for r in receipts if (r.source or "unknown") == x[0] and r.error) / max(x[1], 1),
            )
            recs.append(
                f"Source '{best_source[0]}' has the best error rate. "
                "Consider routing more traffic to it."
            )

        if not recs:
            recs.append("Looking good. Trust score is healthy and costs are reasonable.")

        return recs
