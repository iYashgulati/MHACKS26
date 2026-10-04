import { describe, expect, test } from "bun:test";
import {
  completionNeedsInput,
  formatCompletion,
  type CompletionBody,
} from "./completion";

const routine: CompletionBody = {
  event: "Stop",
  sessionId: "abc",
  assistantMessage: "Based on git status, the build directory does not exist.",
  significance: "routine",
  reasons: [],
  added: 0,
  removed: 0,
  files: [],
  diffstat: "0 files changed, +0/-0",
};

describe("formatCompletion", () => {
  test("includes Claude's actual final terminal response", () => {
    expect(formatCompletion(routine)).toBe(
      "Agent turn finished\n\nBased on git status, the build directory does not exist.",
    );
  });

  test("does not report repository-wide dirtiness as task changes", () => {
    expect(formatCompletion({
      ...routine,
      significance: "review",
      reasons: ["touched auth.ts"],
      diffstat: "21 files changed, +713/-45",
    })).toBe(
      "Agent turn finished\n\nBased on git status, the build directory does not exist.",
    );
  });

  test("marks a final question as waiting for user input", () => {
    const question = {
      ...routine,
      assistantMessage: "Would you like to proceed with the deletion?",
    };
    expect(completionNeedsInput(question)).toBe(true);
    expect(formatCompletion(question)).toStartWith("Needs input\n\n");
  });
});
