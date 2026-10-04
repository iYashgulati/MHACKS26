export type ReplyIntent =
  | { decision: "allow" }
  | { decision: "deny" }
  | { decision: "redirect"; instruction: string }
  | { decision: "question"; answer: string };

const ALLOW = /^(?:y|yes|yeah|yep|sure|allow|approve|go ahead|do it)[.!]?$/i;
const DENY = /^(?:n|no|nope|deny|stop|cancel|don't|do not)[.!]?$/i;

function cleanInstruction(value: string): string {
  return value
    .trim()
    .replace(/^(?:but\s+)?(?:just\s+)?/i, "")
    .replace(/[.!]+$/, "")
    .trim()
    .slice(0, 1000);
}

/** Handle unambiguous replies locally so safety decisions do not depend on an LLM. */
export function classifyObviousReply(text: string): ReplyIntent | null {
  const reply = text.trim();
  if (!reply) return null;

  // "no, run git status instead" / "no, just clear node_modules instead"
  const trailingInstead = reply.match(
    /^no\b[\s,;:!—-]*(.+?)\s+instead[.!]?$/i,
  );
  if (trailingInstead?.[1]) {
    const instruction = cleanInstruction(trailingInstead[1]);
    if (instruction) return { decision: "redirect", instruction };
  }

  // "no, instead run git status"
  const leadingInstead = reply.match(
    /^no\b[\s,;:!—-]*(?:but\s+)?instead[\s,;:—-]+(.+)$/i,
  );
  if (leadingInstead?.[1]) {
    const instruction = cleanInstruction(leadingInstead[1]);
    if (instruction) return { decision: "redirect", instruction };
  }

  if (ALLOW.test(reply)) return { decision: "allow" };
  if (DENY.test(reply)) return { decision: "deny" };
  return null;
}
