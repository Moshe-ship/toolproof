"""ToolProof - Agent tool verification."""

__version__ = "0.3.0"

from toolproof.receipt import Receipt, ReceiptStore, estimate_cost
from toolproof.verifier import Verifier, VerificationResult, AgentClaim, Verdict
from toolproof.trust import TrustScore, TrustReport
from toolproof.proxy import ToolProxy
from toolproof.gate import Gate, Policy, Decision, Action
from toolproof.sdk_patch import patch_openai, patch_anthropic, patch_all

__all__ = [
    "Receipt",
    "ReceiptStore",
    "estimate_cost",
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
    "patch_openai",
    "patch_anthropic",
    "patch_all",
]
