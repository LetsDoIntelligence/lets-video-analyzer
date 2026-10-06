import { describe, expect, it } from "vitest";
import { analyzeEventSchema } from "@/lib/api/schemas";
import fixture from "@/lib/api/fixtures/analyze-events.json";

/**
 * The fixture is produced by the Python backend (apps/api/scripts/dump_contract_fixture.py).
 * If this fails, the backend and the Zod contract have drifted apart.
 */
describe("backend contract fixture", () => {
  it.each(fixture.map((f) => [f.question, f.events] as const))("%s", (_q, events) => {
    expect(events.length).toBeGreaterThan(0);
    for (const e of events) {
      const parsed = analyzeEventSchema.safeParse(e);
      expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true);
    }
  });

  it("covers every reply block type", () => {
    const types = new Set(
      fixture.flatMap((f) =>
        f.events.flatMap((e) => ("blocks" in e ? (e.blocks as { type: string }[]).map((b) => b.type) : [])),
      ),
    );
    expect(types).toEqual(new Set(["stat", "chart", "table", "timestamps"]));
  });
});
