"""Feedback generator — outputs actionable config changes for agent frameworks.

Takes analytics results and generates specific adjustments for:
- Hermes profiles (skill weights, model selection)
- OpenClaw config (tool permissions, routing)
- System prompts (add verification instructions)
- Generic JSON feedback for any framework

This closes the eval loop:
  Run agent -> Record receipts -> Analyze patterns -> Generate feedback -> Improve agent

Usage:
    from toolproof.feedback import FeedbackGenerator

    generator = FeedbackGenerator(analytics_report)
    feedback = generator.generate()

    # Write Hermes-compatible feedback
    generator.write_hermes_feedback("~/.hermes/profiles/nashir/feedback.json")

    # Write OpenClaw-compatible feedback
    generator.write_openclaw_feedback("~/.openclaw/toolproof-feedback.json")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from toolproof.analytics import AnalyticsReport, ToolStats


@dataclass
class ToolFeedback:
    """Feedback for a specific tool."""

    tool_name: str
    action: str  # "keep", "warn", "restrict", "disable"
    reason: str
    suggested_prompt: str = ""
    max_retries: int = 0

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "tool": self.tool_name,
            "action": self.action,
            "reason": self.reason,
        }
        if self.suggested_prompt:
            d["suggested_prompt"] = self.suggested_prompt
        if self.max_retries:
            d["max_retries"] = self.max_retries
        return d


@dataclass
class Feedback:
    """Complete feedback package."""

    trust_score: float
    grade: str
    model_recommendation: str = ""
    system_prompt_additions: list[str] = field(default_factory=list)
    tool_feedback: list[ToolFeedback] = field(default_factory=list)
    cost_actions: list[str] = field(default_factory=list)
    general_recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "trust_score": round(self.trust_score, 4),
            "grade": self.grade,
            "model_recommendation": self.model_recommendation,
            "system_prompt_additions": self.system_prompt_additions,
            "tool_feedback": [t.to_dict() for t in self.tool_feedback],
            "cost_actions": self.cost_actions,
            "general_recommendations": self.general_recommendations,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class FeedbackGenerator:
    """Generate actionable feedback from analytics."""

    def __init__(self, report: AnalyticsReport):
        self.report = report

    def generate(self) -> Feedback:
        """Generate complete feedback package."""
        r = self.report
        grade = self._grade(r.trust_score)

        feedback = Feedback(
            trust_score=r.trust_score,
            grade=grade,
        )

        # Model recommendation based on trust score
        if r.trust_score < 0.5:
            feedback.model_recommendation = (
                "Current model hallucinates tool calls frequently. "
                "Switch to a more capable model (Claude Opus, GPT-4o) or reduce tool count."
            )
        elif r.trust_score < 0.8:
            feedback.model_recommendation = (
                "Model struggles with some tools. Consider adding explicit tool-use "
                "instructions or switching to a model with better function-calling accuracy."
            )

        # System prompt additions
        if r.trust_score < 0.9:
            feedback.system_prompt_additions.append(
                "IMPORTANT: Only use tools when you have actual data to work with. "
                "Never fabricate tool results. If a tool call fails, say so explicitly."
            )
        if r.worst_tools:
            tool_names = [t.name for t in r.worst_tools[:3]]
            feedback.system_prompt_additions.append(
                f"The following tools have high error rates and should be used carefully: "
                f"{', '.join(tool_names)}. Double-check arguments before calling them."
            )

        # Per-tool feedback
        for ts in r.tool_stats:
            tf = self._tool_feedback(ts)
            if tf:
                feedback.tool_feedback.append(tf)

        # Cost actions
        if r.cache_efficiency < 0.1 and r.total_cost > 0.05:
            feedback.cost_actions.append(
                "Enable prompt caching: place tool definitions in the system prompt "
                "prefix so they can be cached across turns."
            )
        if r.cost_anomalies:
            feedback.cost_actions.append(
                f"Set per-call cost limit to prevent anomalies. "
                f"Worst anomaly was {r.cost_anomalies[0].multiplier:.0f}x average cost."
            )
        if r.total_cost > 1.0:
            feedback.cost_actions.append(
                "Consider using a smaller model for simple tool calls "
                "(Haiku for lookup tools, Sonnet for complex reasoning)."
            )

        feedback.general_recommendations = r.recommendations

        return feedback

    def _tool_feedback(self, ts: ToolStats) -> ToolFeedback | None:
        """Generate feedback for a single tool."""
        if ts.total_calls < 2:
            return None

        if ts.error_rate > 0.5:
            return ToolFeedback(
                tool_name=ts.name,
                action="restrict",
                reason=f"Error rate {ts.error_rate:.0%} — more than half of calls fail",
                suggested_prompt=(
                    f"When using {ts.name}, verify the arguments are valid before calling. "
                    f"This tool has a high failure rate."
                ),
                max_retries=1,
            )

        if ts.error_rate > 0.2:
            return ToolFeedback(
                tool_name=ts.name,
                action="warn",
                reason=f"Error rate {ts.error_rate:.0%} — consider improving tool definition",
                suggested_prompt=f"Be careful with {ts.name} — check arguments thoroughly.",
            )

        if ts.avg_cost > 0.05:
            return ToolFeedback(
                tool_name=ts.name,
                action="warn",
                reason=f"High average cost ${ts.avg_cost:.4f} per call",
            )

        return None

    def _grade(self, score: float) -> str:
        pct = score * 100
        if pct >= 95: return "A"
        if pct >= 85: return "B"
        if pct >= 70: return "C"
        if pct >= 50: return "D"
        return "F"

    def write_hermes_feedback(self, path: str | Path) -> None:
        """Write feedback in Hermes-compatible format."""
        feedback = self.generate()
        hermes_config = {
            "toolproof_feedback": {
                "generated_at": "auto",
                "trust_score": feedback.trust_score,
                "grade": feedback.grade,
                "system_prompt_additions": feedback.system_prompt_additions,
                "tool_overrides": {
                    tf.tool_name: {
                        "action": tf.action,
                        "max_retries": tf.max_retries,
                        "note": tf.reason,
                    }
                    for tf in feedback.tool_feedback
                },
            }
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(hermes_config, indent=2, ensure_ascii=False), encoding="utf-8")

    def write_openclaw_feedback(self, path: str | Path) -> None:
        """Write feedback in OpenClaw-compatible format."""
        feedback = self.generate()
        oc_config = {
            "toolproof": {
                "trust_score": feedback.trust_score,
                "grade": feedback.grade,
                "prompt_additions": feedback.system_prompt_additions,
                "tool_policies": {
                    tf.tool_name: tf.action
                    for tf in feedback.tool_feedback
                },
                "cost_budget": {
                    "alert_threshold": 0.50,
                    "session_limit": 10.00,
                },
            }
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(oc_config, indent=2, ensure_ascii=False), encoding="utf-8")

    def write_generic(self, path: str | Path) -> None:
        """Write feedback as generic JSON."""
        feedback = self.generate()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(feedback.to_json(), encoding="utf-8")
