"""ToolProof - Agent tool verification."""

__version__ = "0.5.0"

from toolproof.receipt import Receipt, ReceiptStore, estimate_cost, redact_sensitive
from toolproof.verifier import Verifier, VerificationResult, AgentClaim, Verdict
from toolproof.trust import TrustScore, TrustReport
from toolproof.proxy import ToolProxy
from toolproof.gate import Gate, Policy, Decision, Action
from toolproof.analytics import Analyzer, AnalyticsReport
from toolproof.feedback import FeedbackGenerator, Feedback
from toolproof.sdk_patch import patch_openai, patch_anthropic, patch_all
from toolproof.mtg_bridge import from_mtg_violation, receipt_from_mtg_run

__all__ = [
    "Receipt",
    "ReceiptStore",
    "estimate_cost",
    "redact_sensitive",
    "Verifier",
    "VerificationResult",
    "AgentClaim",
    "Verdict",
    "TrustScore",
    "TrustReport",
    "ToolProxy",
    "Gate",
    "Policy",
    "Decision",
    "Action",
    "Analyzer",
    "AnalyticsReport",
    "FeedbackGenerator",
    "Feedback",
    "patch_openai",
    "patch_anthropic",
    "patch_all",
    "from_mtg_violation",
    "receipt_from_mtg_run",
]
