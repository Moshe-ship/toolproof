"""ToolProof - Agent tool verification."""

__version__ = "0.2.0"

from toolproof.receipt import Receipt, ReceiptStore
from toolproof.verifier import Verifier, VerificationResult, AgentClaim, Verdict
from toolproof.trust import TrustScore, TrustReport
from toolproof.proxy import ToolProxy
from toolproof.sdk_patch import patch_openai, patch_anthropic, patch_all

__all__ = [
    "Receipt",
    "ReceiptStore",
    "Verifier",
    "VerificationResult",
    "AgentClaim",
    "Verdict",
    "TrustScore",
    "TrustReport",
    "ToolProxy",
    "patch_openai",
    "patch_anthropic",
    "patch_all",
]
