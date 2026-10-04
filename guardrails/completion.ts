export type CompletionBody = {
  event: "Stop" | "StopFailure" | string;
  sessionId?: string;
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
  return `Complete\n\n${finalMessage.slice(0, 3500)}`;
}
