# X Post: ToolProof Launch (Banger)

---

## POST (long format, native X)

Just shipped ToolProof.

It catches AI agents lying about tool calls.

The problem:

- Your agent says "I searched the database." It didn't.
- Your agent says "I read that file." It fabricated the content.
- 91.1% hallucination rate on tool calls under adversarial conditions
- Nobody checks. Every observability tool logs what the agent SAID, not what actually HAPPENED.

What ToolProof does:

+ Sits between your agent and its tools
+ Records every tool call with a signed receipt (SHA-256 + HMAC)
+ Cross-references agent claims against actual execution
+ Returns a trust score: VERIFIED / UNVERIFIED / TAMPERED
+ Zero config. One command.

How to use it:

- toolproof wrap -- python agent.py (auto-intercept everything)
- toolproof proxy --target localhost:3000 (HTTP proxy mode)
- toolproof.patch_openai() (one-line SDK patch)
- toolproof import-claude (reads your @claudecode sessions)
- toolproof ci --min-trust 0.8 (CI gate for deployments)
- toolproof analyze (find patterns in your receipt history)
- toolproof feedback --format hermes (auto-generate agent config fixes)

What makes this different from everything else out there:

+ Not another observability dashboard
+ Cryptographic proof, not just logs
+ Pre-execution gating (blocks dangerous calls BEFORE they run)
+ Token cost tracking per tool call (catches the @AnthropicAI broken caching issue)
+ Eval-driven optimization loop (inspired by @karpathy — measure everything, improve systematically)
+ Native @OpenClaw plugin (published to ClawHub, thanks @steipete)
+ Works with @claudecode, Hermes, @OpenClaw, @OpenAI, @AnthropicAI
+ 71 tests. 18 modules. 17 commands. MIT license. Runs locally.

The eval loop (@karpathy style):

+ toolproof analyze — finds which tools get hallucinated most, cost anomalies, cache efficiency
+ toolproof feedback — generates actionable config changes for your agent
+ Outputs Hermes profiles, @OpenClaw config, or generic JSON
+ Run -> Record -> Analyze -> Feedback -> Improve -> Repeat
+ You don't improve what you don't measure

The @AnthropicAI problem this solves:

- March 2026: per-turn tool limit dropped from 60+ to ~10-20
- Prompt caching broke silently, inflating costs 10-20x
- 5-hour @claudecode sessions exhausted in 19 minutes
- ToolProof shows you exactly which calls burn your tokens
- Set cost limits. Block calls that exceed budget. Before they execute.

Pre-execution gating:

+ Define policies: allow / block / review
+ Block "rm -rf" and "DROP TABLE" automatically
+ Review any access to .env or credentials
+ Set per-call cost limits ($0.50 max)
+ Set session cost limits ($10 max)
+ First matching rule wins

Security:

+ 2 rounds of pen-testing. 14 findings fixed. 6 bypasses caught and patched.
+ Timing-safe hash comparison (no oracle attacks)
+ SSRF prevention in the proxy
+ Symlink detection on all file paths
+ ReDoS-safe regex with hard timeouts
+ Secret redaction (20+ patterns)

This aligns with:

- @Microsoft Agent Governance Toolkit (released April 2)
- AEGIS pre-execution firewall papers
- W3C Agentic Integrity Verification draft
- EU AI Act enforcement (August 2026)

71 tests passing. pip install toolproof.

github.com/Moshe-ship/toolproof
https://moshe-ship.github.io/toolproof/

Built on top of:

+ @AnthropicAI / @claudecode — where I first saw the problem
+ @OpenAI — for the tool_use format standard
+ @steipete and @OpenClaw — ToolProof is a native OpenClaw plugin because Peter built the platform to be extensible
+ @karpathy — the eval-driven philosophy. Measure everything. The analytics loop exists because of his work.
+ @LangChainAI — tool scoping patterns informed the gating design
+ @Microsoft Agent Governance Toolkit — validated pre-execution gating
+ AEGIS research — the firewall architecture
+ W3C — the receipt format targets the Agentic Integrity spec

Built by Musa the Carpenter.
Thanks to the Saudi AI Community for testing and feedback.

---

## Media (4 images — open HTML files in browser, screenshot):

1. content/media/hero-terminal.html — Terminal showing trust score
2. content/media/flow-diagram.html — Architecture diagram
3. content/media/trust-score-card.html — Grade card
