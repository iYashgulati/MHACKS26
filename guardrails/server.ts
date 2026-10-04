import { Spectrum } from "spectrum-ts";
import { terminal } from "spectrum-ts/providers/terminal";
import { imessage } from "spectrum-ts/providers/imessage";
import Anthropic from "@anthropic-ai/sdk";
import { fileURLToPath } from "node:url";
import { classifyObviousReply, type ReplyIntent } from "./reply";
import {
  completionNeedsInput,
  formatCompletion,
  type CompletionBody,
} from "./completion";

type Decision = "allow" | "deny";
type Resolution = { decision: Decision; redirect?: string };
type HistoryDecision = Decision | "redirect";

type Pending = {
  action: string;
  reason: string;
  task: string;
  sessionId: string;
  cwd: string;
  resolve: (result: Resolution) => void;
  timer: ReturnType<typeof setTimeout>;
};

type ClaudeSession = {
  sessionId: string;
  cwd: string;
};

type QueuedRedirect = ClaudeSession & {
  instruction: string;
  replyMessage: any;
};

const TIMEOUT_MS = 10 * 60 * 1000;
const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const pending = new Map<string, Pending>();
const history: Array<{ action: string; decision: HistoryDecision }> = [];
const completionKeys = new Set<string>();
const processedMessageIds = new Set<string>();
const recentInboundReplies = new Map<string, number>();
let activeSpace: any = null;
let completionReplyTarget: any = null;
let awaitingClaudeSession: ClaudeSession | null = null;
let phoneClaudeRunning = false;
let queuedRedirect: QueuedRedirect | null = null;

const anthropic = new Anthropic();

const convo = await Spectrum({
  providers: [terminal.config(), imessage.config()],
});

const MY_PHONE = process.env.MY_PHONE!;
try {
  const im = imessage(convo);
  const me = await im.user(MY_PHONE);
  activeSpace = await im.space.create(me);
  console.log("imessage space ready");
} catch (e) {
  await Bun.write("err.log", String(e) + "\n\n" + (e as Error).stack);
  console.error("imessage failed, see err.log");
}


console.log("spectrum up");

Bun.serve({
  port: 8787,
  async fetch(req) {
    const url = new URL(req.url);

    if (url.pathname === "/health") {
      return Response.json({ ok: true, hasSpace: !!activeSpace });
    }

    if (url.pathname === "/notify" && req.method === "POST") {
      const body = await req.json() as { action: string; reason?: string };
      if (activeSpace) {
        activeSpace.send(
          `Blocked — Claude tried to run:\n\n${body.action}\n\n` +
          `${body.reason ?? ""}\n\nNo action needed, it was stopped.`
        );
      }
      return Response.json({ ok: true });
    }

    if (url.pathname === "/completion" && req.method === "POST") {
      const body = await req.json() as CompletionBody;
      const key = JSON.stringify([
        body.event,
        body.sessionId ?? "",
        body.assistantMessage ?? "",
        body.diffstat,
      ]);

      if (completionKeys.has(key)) {
        return Response.json({ ok: true, duplicate: true });
      }
      completionKeys.add(key);
      if (completionKeys.size > 100) {
        const oldest = completionKeys.values().next().value;
        if (oldest) completionKeys.delete(oldest);
      }

      const completionSpace = activeSpace;
      if (!completionSpace) {
        return Response.json({ ok: false, why: "no conversation open" });
      }

      // A redirect is a separate Claude turn. Suppress the original denied
      // turn's explanation and run the user's replacement instruction after
      // that turn has fully released the session.
      if (
        queuedRedirect &&
        queuedRedirect.sessionId === body.sessionId
      ) {
        const redirect = queuedRedirect;
        queuedRedirect = null;
        awaitingClaudeSession = null;
        // Let this Stop-hook response return before resuming the same session.
        setTimeout(() => launchRedirectWhenIdle(redirect), 250);
        return Response.json({ ok: true, redirected: true });
      }

      // The Stop hook already provides Claude's final response. Forward it
      // directly so completion delivery never waits on another model call.
      const completionText = formatCompletion(body);
      if (completionNeedsInput(body) && body.sessionId && body.cwd) {
        awaitingClaudeSession = {
          sessionId: body.sessionId,
          cwd: body.cwd,
        };
      } else {
        awaitingClaudeSession = null;
      }
      const replyTarget = completionReplyTarget;
      if (replyTarget) {
        completionReplyTarget = null;
        try {
          await replyTarget.reply(completionText);
        } catch (error) {
          console.error("completion reply failed; sending normally:", error);
          await completionSpace.send(completionText);
        }
      } else {
        await completionSpace.send(completionText);
      }
      return Response.json({ ok: true });
    }

    if (url.pathname !== "/approval" || req.method !== "POST") {
      return new Response("not found", { status: 404 });
    }

    const body = await req.json() as {
      action: string;
      reason?: string;
      task?: string;
      sessionId?: string;
      cwd?: string;
    };

    if (!activeSpace) {
      return Response.json({
        decision: "deny",
        why: "no conversation open",
      });
    }

    const approvalSpace = activeSpace;
    const approvalSpaceId = approvalSpace.id;

    if (pending.has(approvalSpaceId)) {
      return Response.json({
        decision: "deny",
        why: "another request pending",
      });
    }

    const resolution = await new Promise<Resolution>((resolve) => {
      const timer = setTimeout(async () => {
        pending.delete(approvalSpaceId);
        await approvalSpace.send(
          "No response in 10 minutes — denied by default."
        );
        resolve({ decision: "deny" });
      }, TIMEOUT_MS);

      pending.set(approvalSpaceId, {
        action: body.action,
        reason: body.reason ?? "",
        task: body.task ?? "",
        sessionId: body.sessionId ?? "",
        cwd: body.cwd ?? "",
        resolve,
        timer,
      });

      approvalSpace.send(
        `Agent wants to run:\n\n${body.action}\n\n` +
        `${body.reason ?? ""}\n` +
        `Your task was: "${body.task || "unknown"}"\n\n` +
        `Reply yes / no, ask me about it, or tell Claude what to do instead.`
      );
    });

    return Response.json(resolution);
  },
});

console.log("api on :8787");

async function classifyReply(text: string, p: Pending): Promise<ReplyIntent> {
  const obvious = classifyObviousReply(text);
  if (obvious) return obvious;

  const past = history.slice(-3).map(h => `${h.decision}: ${h.action}`).join("; ");

  const system =
    `You gate a coding agent's risky actions. A user is deciding whether to allow one.\n\n` +
    `Their original task: ${p.task || "unknown"}\n` +
    `Proposed action: ${p.action}\n` +
    `Why it was flagged: ${p.reason}\n` +
    (past ? `Their past decisions: ${past}\n` : "") +
    `\nInterpret their reply. Respond ONLY with JSON:\n` +
    `{"decision":"allow"|"deny"|"redirect"|"question","answer":"...","instruction":"..."}\n\n` +
    `- "allow"/"deny" when they are deciding ("yeah go ahead", "nah", "stop")\n` +
    `- "redirect" when they deny this action and clearly request a different action ` +
    `(for example, "no, clear node_modules instead"); copy only the requested new action ` +
    `into "instruction"\n` +
    `- "question" when they are asking rather than deciding; put a short concrete\n` +
    `  explanation in "answer", 2 sentences max, plain language\n` +
    `- unsure → "question", and ask them to confirm`;

  try {
    const res = await anthropic.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 300,
      system,
      messages: [{ role: "user", content: text }],
    });
    const first = res.content[0];
    const raw = first?.type === "text" ? first.text : "{}";
    const parsed = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));
    if (!["allow", "deny", "redirect", "question"].includes(parsed.decision)) {
      throw new Error("invalid reply decision");
    }
    if (parsed.decision === "redirect" && !String(parsed.instruction ?? "").trim()) {
      return { decision: "question", answer: "What should Claude do instead?" };
    }
    if (parsed.decision === "redirect") {
      return {
        decision: "redirect",
        instruction: String(parsed.instruction).trim().slice(0, 1000),
      };
    }
    if (parsed.decision === "question") {
      return {
        decision: "question",
        answer: String(parsed.answer ?? "Please confirm yes, no, or what to do instead."),
      };
    }
    return parsed.decision === "allow"
      ? { decision: "allow" }
      : { decision: "deny" };
  } catch (e) {
    console.error("classifyReply failed:", e);
    return { decision: "deny" };
  }
}

async function runClaudeFromPhone(
  session: ClaudeSession | null,
  prompt: string,
  replyMessage: any,
): Promise<void> {
  const executable = process.env.CLAUDE_BIN || "claude";
  const args = session
    ? [executable, "--resume", session.sessionId, "--print", prompt]
    : [executable, "--print", prompt];
  try {
    const child = Bun.spawn(
      args,
      {
        cwd: session?.cwd || PROJECT_ROOT,
        env: globalThis.process.env,
        stdout: "pipe",
        stderr: "pipe",
      },
    );
    const [stdout, stderr, exitCode] = await Promise.all([
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
      child.exited,
    ]);
    if (exitCode !== 0) {
      console.error("Claude resume failed:", stderr || stdout);
      if (completionReplyTarget === replyMessage) completionReplyTarget = null;
      await replyMessage.reply(
        `Could not continue Claude's session${stderr.trim() ? `: ${stderr.trim().slice(0, 500)}` : "."}`,
      );
    }
  } catch (error) {
    console.error("Claude resume failed:", error);
    if (completionReplyTarget === replyMessage) completionReplyTarget = null;
      await replyMessage.reply("Could not continue Claude's session.");
  } finally {
    phoneClaudeRunning = false;
  }
}

function launchRedirectWhenIdle(redirect: QueuedRedirect): void {
  if (phoneClaudeRunning) {
    setTimeout(() => launchRedirectWhenIdle(redirect), 100);
    return;
  }
  completionReplyTarget = redirect.replyMessage;
  phoneClaudeRunning = true;
  void runClaudeFromPhone(
    { sessionId: redirect.sessionId, cwd: redirect.cwd },
    redirect.instruction,
    redirect.replyMessage,
  );
}

for await (const [space, message] of convo.messages) {
  if (message.direction === "outbound") continue;
  if (message.platform !== "imessage") continue;
  if (message.content.type !== "text") continue;

  const messageKey = `${message.platform}:${message.id}`;
  if (processedMessageIds.has(messageKey)) continue;
  processedMessageIds.add(messageKey);
  if (processedMessageIds.size > 500) {
    const oldest = processedMessageIds.values().next().value;
    if (oldest) processedMessageIds.delete(oldest);
  }

  const replyText = message.content.text;
  // Photon can emit the same inbound iMessage through two representations
  // whose sender ids differ. The normalized text is the stable duplicate key.
  const replyFingerprint = replyText.trim().toLowerCase();
  const now = Date.now();
  const lastSeen = recentInboundReplies.get(replyFingerprint);
  if (lastSeen !== undefined && now - lastSeen < 5_000) continue;
  recentInboundReplies.set(replyFingerprint, now);
  for (const [fingerprint, timestamp] of recentInboundReplies) {
    if (now - timestamp >= 5_000) recentInboundReplies.delete(fingerprint);
  }

  activeSpace = space;

  let pendingSpaceId = space.id;
  let p = pending.get(pendingSpaceId);

  // Photon can surface the same iMessage through two representations with
  // different space ids. There can only be one outstanding approval per
  // bridge, so route the reply to that approval when the exact id misses.
  if (!p && pending.size === 1) {
    const onlyPending = pending.entries().next().value;
    if (onlyPending) {
      [pendingSpaceId, p] = onlyPending;
    }
  }

  if (!p) {
    if (awaitingClaudeSession) {
      if (phoneClaudeRunning) continue;
      const session = awaitingClaudeSession;
      awaitingClaudeSession = null;
      completionReplyTarget = message;
      phoneClaudeRunning = true;
      // Do not await this process: its tool calls may request approval through
      // this same message loop, which must remain free to receive the reply.
      void runClaudeFromPhone(session, replyText, message);
      continue;
    }

    // With no approval or follow-up pending, treat the phone message as a new
    // Claude task. Keep the loop free so any resulting approval can be handled.
    if (phoneClaudeRunning) continue;
    completionReplyTarget = message;
    phoneClaudeRunning = true;
    void runClaudeFromPhone(null, replyText, message);
    continue;
  }

  await space.responding(async () => {
    const intent = await classifyReply(replyText, p);

    if (
      intent.decision === "allow" ||
      intent.decision === "deny" ||
      intent.decision === "redirect"
    ) {
      clearTimeout(p.timer);
      pending.delete(pendingSpaceId);
      history.push({ action: p.action, decision: intent.decision });
      if (intent.decision === "redirect") {
        const instruction = String(intent.instruction).trim().slice(0, 1000);
        completionReplyTarget = message;
        if (p.sessionId && p.cwd) {
          queuedRedirect = {
            sessionId: p.sessionId,
            cwd: p.cwd,
            instruction,
            replyMessage: message,
          };
        }
        p.resolve({ decision: "deny", redirect: instruction });
        await message.reply(
          "Redirected — the original action was denied and Claude received your new instruction."
        );
      } else {
        if (intent.decision === "allow") completionReplyTarget = message;
        p.resolve({ decision: intent.decision });
        await message.reply(
          intent.decision === "allow"
            ? "Allowed — agent proceeding."
            : "Denied — agent stopped."
        );
      }
    } else {
      await message.reply(intent.answer);
    }
  });
}
