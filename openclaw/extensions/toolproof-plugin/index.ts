/**
 * ToolProof OpenClaw Plugin
 *
 * Registers ToolProof as a native OpenClaw plugin:
 * - toolproof-audit tool: agents can verify their own claims
 * - toolproof-report tool: generate trust reports
 * - Hook into tool execution lifecycle
 *
 * Install:
 *   openclaw plugins install clawhub toolproof
 *   # or
 *   Add to openclaw.json: { "plugins": { "toolproof": { "enabled": true } } }
 */

import { definePluginEntry } from "@openclaw/plugin-sdk/server";
import { execSync } from "child_process";
import { existsSync, readFileSync, appendFileSync, mkdirSync } from "fs";
import { join } from "path";
import { createHash, createHmac, randomUUID } from "crypto";

const STORE_PATH =
  process.env.TOOLPROOF_STORE ||
  join(process.env.HOME || "~", ".toolproof", "receipts.jsonl");

const SECRET = process.env.TOOLPROOF_SECRET || "";

interface Receipt {
  id: string;
  timestamp: number;
  tool_name: string;
  arguments: Record<string, unknown>;
  response: unknown;
  error: string | null;
  duration_ms: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  hash: string;
  hmac_sig: string;
  source: string;
  session_id: string;
}

function signReceipt(receipt: Receipt): void {
  const payload = JSON.stringify({
    tool_name: receipt.tool_name,
    arguments: receipt.arguments,
    response: receipt.response,
    error: receipt.error,
    timestamp: receipt.timestamp,
  });

  receipt.hash = createHash("sha256").update(payload, "utf8").digest("hex");

  if (SECRET) {
    receipt.hmac_sig = createHmac("sha256", SECRET)
      .update(payload, "utf8")
      .digest("hex");
  }
}

function appendReceipt(receipt: Receipt): void {
  const dir = join(STORE_PATH, "..");
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
  appendFileSync(STORE_PATH, JSON.stringify(receipt) + "\n", "utf8");
}

function loadReceipts(): Receipt[] {
  if (!existsSync(STORE_PATH)) return [];
  const lines = readFileSync(STORE_PATH, "utf8").split("\n").filter(Boolean);
  return lines.map((line) => JSON.parse(line));
}

function truncate(value: unknown, maxLen = 2000): unknown {
  if (value === null || value === undefined) return value;
  const str = typeof value === "string" ? value : JSON.stringify(value);
  if (str.length <= maxLen) return value;
  if (typeof value === "string") return value.slice(0, maxLen) + "...";
  return str.slice(0, maxLen) + "...";
}

export default definePluginEntry({
  name: "toolproof",
  version: "0.3.0",
  description:
    "Agent tool verification — catches hallucinated tool calls with signed execution receipts",

  setup(api) {
    // =====================================================================
    // Tool: toolproof-audit
    // Agents can explicitly verify their own claims
    // =====================================================================
    api.registerTool({
      name: "toolproof-audit",
      description:
        "Verify a tool call claim against execution receipts. Returns VERIFIED, UNVERIFIED, or TAMPERED.",
      parameters: {
        type: "object",
        properties: {
          tool_name: {
            type: "string",
            description: "Name of the tool that was called",
          },
          arguments: {
            type: "object",
            description: "Arguments that were passed to the tool",
          },
          claimed_response: {
            type: "string",
            description:
              "What the agent claims the tool returned (optional)",
          },
        },
        required: ["tool_name"],
      },
      async execute({ tool_name, arguments: args, claimed_response }) {
        const receipts = loadReceipts();
        const candidates = receipts.filter(
          (r) => r.tool_name === tool_name
        );

        if (candidates.length === 0) {
          return {
            verdict: "UNVERIFIED",
            details: `No receipts found for tool '${tool_name}'`,
            trust_score: 0,
          };
        }

        // Find best match
        const argsStr = JSON.stringify(args || {});
        let bestMatch: Receipt | null = null;
        let bestScore = -1;

        for (const receipt of candidates) {
          const receiptArgs = JSON.stringify(receipt.arguments || {});
          const score =
            receiptArgs === argsStr ? 1.0 : receiptArgs.includes(argsStr) ? 0.5 : 0;
          if (score > bestScore) {
            bestScore = score;
            bestMatch = receipt;
          }
        }

        if (!bestMatch || bestScore < 0.5) {
          return {
            verdict: "TAMPERED",
            details: "Receipt exists but arguments do not match",
            trust_score: bestScore,
            receipt_id: bestMatch?.id,
          };
        }

        // Check response if claimed
        if (claimed_response && bestMatch.response) {
          const actualStr = JSON.stringify(bestMatch.response);
          if (!actualStr.includes(String(claimed_response).slice(0, 100))) {
            return {
              verdict: "TAMPERED",
              details: "Response does not match receipt",
              trust_score: 0.3,
              receipt_id: bestMatch.id,
            };
          }
        }

        return {
          verdict: "VERIFIED",
          details: "Claim matches execution receipt",
          trust_score: 1.0,
          receipt_id: bestMatch.id,
          hash: bestMatch.hash,
        };
      },
    });

    // =====================================================================
    // Tool: toolproof-report
    // Generate trust report for current session
    // =====================================================================
    api.registerTool({
      name: "toolproof-report",
      description:
        "Generate a trust report showing all recorded tool calls, trust score, and any flagged issues.",
      parameters: {
        type: "object",
        properties: {
          format: {
            type: "string",
            enum: ["summary", "detailed", "json"],
            description: "Report format (default: summary)",
          },
          last_n: {
            type: "number",
            description: "Only show last N receipts (default: all)",
          },
        },
      },
      async execute({ format = "summary", last_n }) {
        const allReceipts = loadReceipts();
        const receipts = last_n
          ? allReceipts.slice(-last_n)
          : allReceipts;

        const total = receipts.length;
        const errors = receipts.filter((r) => r.error).length;
        const clean = total - errors;
        const trust = total > 0 ? clean / total : 1.0;

        // Cost tracking
        const totalCost = receipts.reduce(
          (sum, r) => sum + (r.cost_usd || 0),
          0
        );
        const totalTokensIn = receipts.reduce(
          (sum, r) => sum + (r.tokens_in || 0),
          0
        );
        const totalTokensOut = receipts.reduce(
          (sum, r) => sum + (r.tokens_out || 0),
          0
        );

        // Tool breakdown
        const byTool: Record<string, { count: number; errors: number; cost: number }> = {};
        for (const r of receipts) {
          if (!byTool[r.tool_name]) {
            byTool[r.tool_name] = { count: 0, errors: 0, cost: 0 };
          }
          byTool[r.tool_name].count++;
          if (r.error) byTool[r.tool_name].errors++;
          byTool[r.tool_name].cost += r.cost_usd || 0;
        }

        if (format === "json") {
          return { total, errors, trust, totalCost, totalTokensIn, totalTokensOut, byTool };
        }

        // Build text report
        const grade =
          trust >= 0.95
            ? "A"
            : trust >= 0.85
            ? "B"
            : trust >= 0.7
            ? "C"
            : trust >= 0.5
            ? "D"
            : "F";

        let report = `ToolProof Trust Report\n`;
        report += `${"=".repeat(40)}\n`;
        report += `Trust Score: ${(trust * 100).toFixed(1)}% (Grade: ${grade})\n`;
        report += `Receipts: ${total} (${errors} errors)\n`;
        report += `Cost: $${totalCost.toFixed(4)}\n`;
        report += `Tokens: ${totalTokensIn} in / ${totalTokensOut} out\n\n`;

        if (format === "detailed") {
          report += `Tool Breakdown:\n`;
          for (const [name, stats] of Object.entries(byTool)) {
            report += `  ${name}: ${stats.count} calls`;
            if (stats.errors) report += ` (${stats.errors} errors)`;
            if (stats.cost > 0) report += ` ($${stats.cost.toFixed(4)})`;
            report += `\n`;
          }
        }

        return report;
      },
    });

    // =====================================================================
    // Hook: Record receipts on tool execution
    // =====================================================================
    const pendingCalls = new Map<string, { timestamp: number; tool_name: string; arguments: Record<string, unknown> }>();

    api.on("tool:execute", (event: { toolCallId: string; name: string; input: Record<string, unknown> }) => {
      pendingCalls.set(event.toolCallId, {
        timestamp: Date.now() / 1000,
        tool_name: event.name,
        arguments: event.input,
      });
    });

    api.on("tool:result", (event: { toolCallId: string; output: unknown; isError?: boolean; usage?: { input_tokens?: number; output_tokens?: number } }) => {
      const pending = pendingCalls.get(event.toolCallId);
      if (!pending) return;
      pendingCalls.delete(event.toolCallId);

      const now = Date.now() / 1000;
      const tokensIn = event.usage?.input_tokens || 0;
      const tokensOut = event.usage?.output_tokens || 0;

      const receipt: Receipt = {
        id: randomUUID(),
        timestamp: pending.timestamp,
        tool_name: pending.tool_name,
        arguments: pending.arguments,
        response: truncate(event.output),
        error: event.isError ? String(event.output).slice(0, 500) : null,
        duration_ms: (now - pending.timestamp) * 1000,
        tokens_in: tokensIn,
        tokens_out: tokensOut,
        cost_usd: estimateCost(tokensIn, tokensOut),
        hash: "",
        hmac_sig: "",
        source: "openclaw",
        session_id: process.env.OPENCLAW_SESSION_ID || "",
      };

      signReceipt(receipt);
      appendReceipt(receipt);
    });
  },
});

/**
 * Estimate cost based on token counts.
 * Uses Claude Sonnet 4.6 pricing as default.
 */
function estimateCost(tokensIn: number, tokensOut: number): number {
  // Sonnet 4.6: $3/M input, $15/M output
  const inputCost = (tokensIn / 1_000_000) * 3.0;
  const outputCost = (tokensOut / 1_000_000) * 15.0;
  return inputCost + outputCost;
}
