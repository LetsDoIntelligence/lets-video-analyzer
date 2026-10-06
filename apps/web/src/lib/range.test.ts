import { describe, expect, it } from "vitest";
import { describeRange, isFullRange, parseTimecode, withEnd, withStart } from "./range";

describe("parseTimecode", () => {
  it("parses common formats", () => {
    expect(parseTimecode("95")).toBe(95);
    expect(parseTimecode("95s")).toBe(95);
    expect(parseTimecode("1:35")).toBe(95);
    expect(parseTimecode("1:02:05")).toBe(3725);
  });
  it("rejects garbage", () => {
    expect(parseTimecode("")).toBeNull();
    expect(parseTimecode("abc")).toBeNull();
    expect(parseTimecode("1:2:3:4")).toBeNull();
  });
});

describe("range editing", () => {
  const r = { start: 30, end: 90 };
  it("keeps start before end", () => {
    expect(withStart(r, 200).start).toBe(89);
    expect(withStart(r, -5).start).toBe(0);
  });
  it("keeps end after start and inside the video", () => {
    expect(withEnd(r, 10, 300).end).toBe(31);
    expect(withEnd(r, 999, 300).end).toBe(300);
  });
});

describe("describeRange", () => {
  it("detects full range", () => {
    expect(isFullRange({ start: 0, end: 300 }, 300)).toBe(true);
    expect(describeRange({ start: 0, end: 300 }, 300)).toBe("Entire video");
    expect(describeRange({ start: 180, end: 360 }, 480)).toBe("3:00 – 6:00");
  });
});
