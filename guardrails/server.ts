import { Spectrum } from "spectrum-ts";
import { terminal } from "spectrum-ts/providers/terminal";
import { imessage } from "spectrum-ts/providers/imessage";
import Anthropic from "@anthropic-ai/sdk";

type Decision = "allow" | "deny";

type Pending = {
  action: string;
  reason: string;
  task: string;
  resolve: (d: Decision) => void;
  timer: ReturnType<typeof setTimeout>;
};

const TIMEOUT_MS = 10 * 60 * 1000;
const pending = new Map<string, Pending>();
const history: Array<{ action: string; decision: Decision }> = [];
let activeSpace: any = null;

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

    if (url.pathname !== "/approval" || req.method !== "POST") {
      return new Response("not found", { status: 404 });
    }

    const body = await req.json() as {
      action: string;
      reason?: string;
      task?: string;
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

    const decision = await new Promise<Decision>((resolve) => {
      const timer = setTimeout(async () => {
        pending.delete(approvalSpaceId);
        await approvalSpace.send(
          "No response in 10 minutes — denied by default."
        );
        resolve("deny");
      }, TIMEOUT_MS);

      pending.set(approvalSpaceId, {
        action: body.action,
        reason: body.reason ?? "",
        task: body.task ?? "",
        resolve,
        timer,
      });

      approvalSpace.send(
        `Agent wants to run:\n\n${body.action}\n\n` +
        `${body.reason ?? ""}\n` +
        `Your task was: "${body.task || "unknown"}"\n\n` +
        `Reply yes / no — or ask me about it.`
      );
    });

    return Response.json({ decision });
  },
});

console.log("api on :8787");

async function classifyReply(text: string, p: Pending) {
  const past = history.slice(-3).map(h => `${h.decision}: ${h.action}`).join("; ");

  const system =
    `You gate a coding agent's risky actions. A user is deciding whether to allow one.\n\n` +
    `Their original task: ${p.task || "unknown"}\n` +
    `Proposed action: ${p.action}\n` +
    `Why it was flagged: ${p.reason}\n` +
    (past ? `Their past decisions: ${past}\n` : "") +
    `\nInterpret their reply. Respond ONLY with JSON:\n` +
    `{"decision":"allow"|"deny"|"question","answer":"..."}\n\n` +
    `- "allow"/"deny" when they are deciding ("yeah go ahead", "nah", "stop")\n` +
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
    const raw = res.content[0].type === "text" ? res.content[0].text : "{}";
    return JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));
  } catch (e) {
    console.error("classifyReply failed:", e);
    return { decision: "deny", answer: "Couldn't interpret that — denying to be safe." };
  }
}

for await (const [space, message] of convo.messages) {
  if (message.direction === "outbound") continue;
  if (message.platform !== "imessage") continue;

  activeSpace = space;
  if (message.content.type !== "text") continue;

  const p = pending.get(space.id);

  if (!p) {
    await message.reply("Nothing pending. I'll text you when the agent tries something risky.");
    continue;
  }

  await space.responding(async () => {
    const intent = await classifyReply(message.content.text, p);

    if (intent.decision === "allow" || intent.decision === "deny") {
      clearTimeout(p.timer);
      pending.delete(space.id);
      history.push({ action: p.action, decision: intent.decision });
      p.resolve(intent.decision);
      await message.reply(
        intent.decision === "allow"
          ? "Allowed — agent proceeding."
          : "Denied — agent stopped."
      );
    } else {
      await message.reply(intent.answer);
    }
  });
}
