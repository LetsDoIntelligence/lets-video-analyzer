import { describe, expect, it } from "vitest";
import { parseSseBuffer } from "@/lib/api/sse";

describe("parseSseBuffer", () => {
  it("returns complete events and keeps the unfinished remainder", () => {
    const { events, rest } = parseSseBuffer('data: {"a":1}\n\ndata: {"b":2}\n\ndata: {"c"');
    expect(events).toEqual(['{"a":1}', '{"b":2}']);
    expect(rest).toBe('data: {"c"');
  });

  it("handles CRLF and ignores non-data lines", () => {
    const { events } = parseSseBuffer(": ping\r\n\r\nevent: x\r\ndata: hi\r\n\r\n");
    expect(events).toEqual(["hi"]);
  });
});
