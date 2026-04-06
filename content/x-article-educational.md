# Your AI Agent Is Lying to You About Tool Calls. Here's the Proof.

Every time your AI agent says "I searched the database" or "I read that file" or "I called the API" — you believe it.

You shouldn't.

I spent the last year building AI agents. Local models on my Mac. Hermes profiles running 21 skills. OpenClaw with 60 Arabic-focused skills. Claude Code sessions that run for hours.

And I kept finding the same thing: agents lie about what tools they actually used.

Not sometimes. Constantly.

---

## The Problem Nobody Talks About

When you give an agent access to tools — file reading, database queries, API calls, web searches — the agent decides when and how to use them. But there's no verification layer. No proof. No receipt.

The agent says "I searched for flights from Riyadh to Jeddah and found 3 options." Did it actually call the search function? Or did it generate a plausible-looking response from training data?

Under adversarial conditions, researchers found a 91.1% tool hallucination rate. The agent doesn't crash. It doesn't say "I can't do that." It fabricates a convincing answer and keeps going.

Think about what that means. Your agent builds a report by "reading" 10 files. Three of those reads never happened. The data in the report is partially real and partially invented. And it all looks the same to you.

---

## Why Logging Doesn't Fix This

You might think: "I have LangSmith. I have Langfuse. I have observability."

Those tools trace the conversation. They show you what the LLM said. But they don't independently verify that a tool was executed. They record the agent's claim, not the ground truth.

It's like asking a witness what happened versus checking the security camera. The witness tells you a story. The camera shows you what actually happened.

We needed security cameras for agent tool calls. They didn't exist. So I built one.

---

## What ToolProof Does

ToolProof sits between your agent and its tools. Every tool call passes through ToolProof on the way to the real tool.

Here's the flow:

1. Agent decides to call a tool (search_database, read_file, whatever)
2. The call goes through ToolProof
3. ToolProof records: tool name, arguments, timestamp
4. ToolProof forwards the call to the actual tool
5. The real tool returns its response
6. ToolProof records the real response
7. ToolProof signs everything with SHA-256 (optional HMAC for tamper-proofing)
8. ToolProof stores a receipt
9. The response goes back to the agent normally

The agent doesn't know ToolProof is there. It gets the same response it would have gotten without it.

Later — after the agent is done — you verify. You take what the agent claimed it did and cross-reference it against the receipts.

Three possible outcomes:

VERIFIED means the agent's claim matches a receipt. The tool was actually called with those arguments and returned what the agent says it returned.

UNVERIFIED means no matching receipt exists. The agent claims it called a tool, but ToolProof has no record of that call ever happening. This is a hallucination.

TAMPERED means a receipt exists for that tool call, but the agent's claimed output doesn't match what the tool actually returned. The agent called the tool but then lied about the results. This is worse than hallucination — it's fabrication on top of real execution.

---

## The Trust Score

After verification, ToolProof computes a trust score:

trust = verified claims / total claims

If an agent made 20 tool call claims and 18 match receipts, 1 has no receipt, and 1 doesn't match — that's 18/20 = 90% trust.

Grade A means 95% or higher. The agent is trustworthy.
Grade B means 85-94%. Mostly good, a few gaps.
Grade C means 70-84%. Significant unverified claims.
Grade D means 50-69%. Coin flip reliability.
Grade F means below 50%. The agent is lying more than it's telling the truth.

---

## Zero Configuration

The number one reason developer tools don't get adopted: setup friction.

ToolProof has three zero-config modes:

The first is wrap mode. You prefix your existing command:

    toolproof wrap -- python agent.py

ToolProof starts a local proxy, sets the right environment variables, runs your command, then shows you the receipts. One line. No code changes.

The second is proxy mode. You point it at your tool server:

    toolproof proxy --target http://localhost:3000

Every request to port 8080 gets forwarded to port 3000, and every request/response pair gets a receipt. Your agent talks to 8080 instead of 3000. Done.

The third is SDK patching. One line of Python:

    import toolproof
    toolproof.patch_openai()

This monkey-patches the OpenAI SDK so every chat completion with tools generates receipts automatically. Same for Anthropic. No proxy needed.

---

## The Anthropic Problem

In March 2026, Anthropic reduced the per-turn tool call limit from 60-80 calls down to roughly 10-20. At the same time, their prompt caching system broke silently. Tool definitions that should have been cached were being reprocessed at full token cost, inflating bills by 10-20x.

Developers were exhausting 5-hour Claude Code session limits in 19 minutes.

ToolProof tracks token costs on every receipt: tokens_in, tokens_out, cache_read, cost_usd. If your caching is broken, you see it immediately. If one tool call is burning $2 when it should cost $0.02, you see it immediately.

You can also set cost limits. Per-call limits. Per-session limits. ToolProof blocks the call before it executes if it would exceed your budget. This is pre-execution gating — your agent can't drain your API credits even if it goes rogue.

---

## Pre-Execution Gating

This is the feature that aligns ToolProof with where the industry is heading.

Microsoft released their Agent Governance Toolkit on April 2, 2026. The AEGIS research papers describe pre-execution firewalls. The W3C proposed an Agentic Integrity Verification community group in March 2026. The EU AI Act becomes enforceable in August 2026.

Everyone is realizing: we need to check tool calls BEFORE they execute, not just audit them after.

ToolProof's policy engine works like this. You define rules:

    Block: Bash commands containing "rm -rf" or "DROP TABLE"
    Review: Any access to .env files or credentials
    Allow: Everything else

    Max cost per call: $0.50
    Max session cost: $10.00

First matching rule wins. If a tool call hits a "block" rule, it never executes. If it hits a "review" rule, it's held for human approval. If the estimated cost exceeds your limit, it's blocked.

This turns ToolProof from a verification tool into a safety layer.

---

## OpenClaw Native

I built mkhlab — the first Arabic-first OpenClaw plugin, with 60 skills covering everything from prayer times to Arabic NLP to Saudi government APIs.

ToolProof is built to be an OpenClaw plugin the same way. It uses the OpenClaw plugin SDK. It registers tools via api.registerTool(). It hooks into tool:execute and tool:result events.

When you install ToolProof in OpenClaw, every skill execution across every plugin gets a signed receipt. Automatically. No configuration.

It's published to ClawHub. One command to install.

---

## Who This Is For

If you run AI agents that use tools — any tools — you need verification.

If you use Claude Code, the import-claude command reads your session logs and generates receipts from every tool_use/tool_result pair.

If you run Hermes with local models, the import-hermes command reads your profile logs.

If you run OpenClaw, the hook records everything natively.

If you use the OpenAI or Anthropic SDKs, one line of Python patches them.

If you use any HTTP-based tool server, the proxy mode handles it.

If you run CI pipelines with agents, the ci command gives you a pass/fail gate.

---

## What's Next

ToolProof is version 0.3.0. MIT licensed. 63 tests passing.

It works today. Right now. pip install toolproof.

The codebase is intentionally minimal. Python. Three dependencies: rich for terminal output, httpx for HTTP, click for CLI. No framework. No cloud. No account. Everything runs locally. Your receipts stay on your machine.

Agents will only get more autonomous. They'll manage servers, handle finances, interact with real systems. The question isn't whether we need tool verification — it's whether we'll have it in place before something goes wrong.

I'd rather build the safety layer now than explain the outage later.

---

github.com/Moshe-ship/toolproof

Built by Musa the Carpenter. With input from the Saudi AI Community.
