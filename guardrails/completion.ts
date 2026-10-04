export type CompletionBody = {
  event: "Stop" | "StopFailure" | string;
  sessionId?: string;
  cwd?: string;
  assistantMessage?: string;
  significance: "routine" | "review";
  reasons: string[];
  added: number;
  removed: number;
  files: string[];
  diffstat: string;
  error?: string;
  errorDetails?: string;
};

/** True when Claude's final response is asking the user to continue the turn. */
export function completionNeedsInput(body: CompletionBody): boolean {
  if (body.event === "StopFailure") return false;
  const message = body.assistantMessage?.trim() ?? "";
  return message.endsWith("?");
}

/** Format Claude's actual final response without another network round trip. */
export function formatCompletion(body: CompletionBody): string {
  if (body.event === "StopFailure") {
    const detail = body.errorDetails || body.assistantMessage || "No details provided.";
    return `Claude failed — ${body.error || "unknown error"}: ${detail}`.slice(0, 4000);
  }

  const finalMessage = body.assistantMessage?.trim() || "Claude finished the turn.";
  // The payload's diff describes the whole working tree relative to HEAD,
  // not necessarily changes made during this turn. Do not present it as a
  // task-specific result.
  const label = completionNeedsInput(body) ? "Needs input" : "Agent turn finished";
  return `${label}\n\n${finalMessage.slice(0, 3500)}`;
}
