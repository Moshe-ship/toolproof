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
- toolproof import-claude (reads your Claude Code sessions)
- toolproof ci --min-trust 0.8 (CI gate for deployments)

What makes this different from everything else out there:

+ Not another observability dashboard
+ Cryptographic proof, not just logs
+ Pre-execution gating (blocks dangerous calls BEFORE they run)
+ Token cost tracking per tool call (catches the Anthropic broken caching issue)
+ Native OpenClaw plugin (published to ClawHub)
+ Works with Claude Code, Hermes, OpenClaw, OpenAI, Anthropic
+ 63 tests. MIT license. Three dependencies. Runs locally.

The Anthropic problem this solves:

- March 2026: per-turn tool limit dropped from 60+ to ~10-20
- Prompt caching broke silently, inflating costs 10-20x
- 5-hour Claude Code sessions exhausted in 19 minutes
- ToolProof shows you exactly which calls burn your tokens
- Set cost limits. Block calls that exceed budget. Before they execute.

Pre-execution gating:

+ Define policies: allow / block / review
+ Block "rm -rf" and "DROP TABLE" automatically
+ Review any access to .env or credentials
+ Set per-call cost limits ($0.50 max)
+ Set session cost limits ($10 max)
+ First matching rule wins

This aligns with:

- Microsoft Agent Governance Toolkit (released April 2)
- AEGIS pre-execution firewall papers
- W3C Agentic Integrity Verification draft
- EU AI Act enforcement (August 2026)

63 tests passing. pip install toolproof.

github.com/Moshe-ship/toolproof

Built by Musa the Carpenter.
Thanks to the Saudi AI Community for the input.

---

## Media needed (4 images):

1. HERO IMAGE — Dark terminal showing toolproof command output with trust score
2. DIAGRAM — Agent -> ToolProof Proxy -> Real Tool -> Receipt flow
3. TRUST SCORE CARD — The grade card (A/B/C/D/F) with colors
4. BEFORE/AFTER — "Without ToolProof: Agent claims, you trust" vs "With ToolProof: Agent claims, receipts verify"
