# X Thread: Educational — How Agents Lie About Tool Calls

---

## Tweet 1 (Hook)

Your AI agent says "I searched the database and found 3 admin users."

It didn't search anything. It made that up.

91.1% tool hallucination rate under adversarial conditions. Here's what's actually happening and how to catch it:

---

## Tweet 2 (The Problem)

When you give an agent tools — search, read files, call APIs — you assume it actually uses them.

But agents can:
- Claim they called a tool when they didn't
- Return fabricated results that look real
- Mix real and hallucinated data in the same response

Nobody checks. Until now.

---

## Tweet 3 (Why It Matters)

This isn't theoretical.

A research team tested tool-augmented LLMs and found agents fabricate tool outputs 91.1% of the time when the tool isn't available but the agent thinks it should be.

The agent doesn't crash. It doesn't say "I can't do that." It makes up a plausible response and keeps going.

---

## Tweet 4 (Real Example)

Here's what this looks like in practice:

You: "Check if user #4521 exists in the database"

Agent (claims): "I searched the database. User #4521 is John Smith, created on March 15."

Reality: The agent never called the database. John Smith doesn't exist. The agent invented a person.

---

## Tweet 5 (Why Existing Tools Don't Help)

Logging doesn't solve this.

Observability tools like LangSmith, Braintrust, Langfuse — they show you what the LLM said it did. They trace the conversation.

But they don't cryptographically prove that a tool was actually executed. There's a difference between "the agent said it searched" and "the search actually happened."

---

## Tweet 6 (The Solution)

ToolProof sits between the agent and its tools.

Every tool call goes through ToolProof first. It:
1. Records the actual call (function, arguments, timestamp)
2. Captures the real response from the tool
3. Signs everything with SHA-256
4. Stores a tamper-proof receipt

Later, you compare what the agent claims against the receipts.

---

## Tweet 7 (How Verification Works)

Three possible verdicts:

VERIFIED — The agent's claim matches a receipt. The tool was actually called with those arguments.

UNVERIFIED — No matching receipt exists. The agent may have hallucinated the entire tool call.

TAMPERED — A receipt exists, but the agent's claimed output doesn't match what the tool actually returned.

---

## Tweet 8 (Zero Config)

You don't need to change your code.

Option 1 — Wrap your command:
toolproof wrap -- python agent.py

Option 2 — Proxy mode:
toolproof proxy --target http://localhost:3000

Option 3 — One-line SDK patch:
import toolproof
toolproof.patch_openai()

Every tool call gets a receipt. Automatically.

---

## Tweet 9 (Trust Score)

After a session, ToolProof gives you a trust score:

trust = verified / (verified + unverified + tampered)

Grade A: 95%+ (agent is trustworthy)
Grade C: 70-84% (some claims unverified)
Grade F: below 50% (agent is lying)

You can use this in CI to gate deployments.

---

## Tweet 10 (Cost Tracking Bonus)

Every receipt also tracks token cost.

tokens_in, tokens_out, cache_read, cost_usd — per tool call.

Anthropic's broken prompt caching inflated costs 10-20x for tool-heavy workflows in March 2026. ToolProof would have caught that immediately. You'd see exactly which calls were burning your budget.

---

## Tweet 11 (OpenClaw Native)

ToolProof is also a native OpenClaw plugin.

Hook into tool:execute and tool:result events. Every skill execution gets a signed receipt automatically. Works alongside mkhlab, tool-guard, any plugin.

Published to ClawHub. One command install.

---

## Tweet 12 (CTA)

pip install toolproof

GitHub: github.com/Moshe-ship/toolproof

63 tests passing. MIT licensed. Zero dependencies beyond rich, httpx, click.

Works with Claude Code, Hermes, OpenClaw, OpenAI, Anthropic, or any HTTP-based tool server.

Agents lie. Receipts don't.

---

## Thread Notes

- Thank the Saudi AI Community in a reply after the thread
- No emojis in any tweet
- Each tweet should be standalone readable but flow as a thread
- Use line breaks for readability, not walls of text
