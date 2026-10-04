import { describe, expect, test } from "bun:test";
import { classifyObviousReply } from "./reply";

describe("classifyObviousReply", () => {
  test("recognizes trailing-instead redirects", () => {
    expect(classifyObviousReply("no, run git status instead")).toEqual({
      decision: "redirect",
      instruction: "run git status",
    });
    expect(classifyObviousReply("no, just clear node_modules instead")).toEqual({
      decision: "redirect",
      instruction: "clear node_modules",
    });
  });

  test("recognizes leading-instead redirects", () => {
    expect(classifyObviousReply("no, instead run npm test")).toEqual({
      decision: "redirect",
      instruction: "run npm test",
    });
  });

  test("keeps plain decisions as decisions", () => {
    expect(classifyObviousReply("yes")).toEqual({ decision: "allow" });
    expect(classifyObviousReply("no")).toEqual({ decision: "deny" });
  });

  test("leaves ambiguous replies for Haiku", () => {
    expect(classifyObviousReply("is this command safe?")).toBeNull();
  });
});
