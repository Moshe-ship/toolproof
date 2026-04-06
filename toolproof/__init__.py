"""ToolProof - Agent tool verification."""

__version__ = "0.4.0"

from toolproof.receipt import Receipt, ReceiptStore, estimate_cost, redact_sensitive
from toolproof.verifier import Verifier, VerificationResult, AgentClaim, Verdict
from toolproof.trust import TrustScore, TrustReport
from toolproof.proxy import ToolProxy
from toolproof.gate import Gate, Policy, Decision, Action
from toolproof.analytics import Analyzer, AnalyticsReport
from toolproof.feedback import FeedbackGenerator, Feedback
from toolproof.sdk_patch import patch_openai, patch_anthropic, patch_all

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
]
