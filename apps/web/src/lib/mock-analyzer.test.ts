import { describe, expect, it } from "vitest";
import type { ScopeInfo } from "@/lib/chat";
import { bucketSize, buildReply, histogram, parsePrompt, parseTimeWindow } from "./mock-analyzer";


const scope: ScopeInfo = {
  videoId: "v1",
  videoName: "Test video",
  start: 0,
  end: 300,
  duration: 300,
  label: "Entire video",
};

describe("parsePrompt", () => {
  it("detects subject, colour and helmets", () => {
    expect(parsePrompt("How many red cars?").subject.plural).toBe("cars");
    expect(parsePrompt("How many red cars?").color).toBe("red");
    expect(parsePrompt("How many people with helmets?").helmets).toBe(true);
    expect(parsePrompt("How many trucks?").subject.plural).toBe("trucks");
  });
});

describe("parseTimeWindow", () => {
  it("handles 'first N sec'", () => {
    expect(parseTimeWindow("cars in the first 30 sec", scope)).toMatchObject({ start: 0, end: 30 });
  });
  it("handles 'from 3 to 6 minutes'", () => {
    const w = parseTimeWindow("analyze the video from 3 to 6 minutes", { ...scope, duration: 480, end: 480 });
    expect(w).toMatchObject({ start: 180, end: 360, fromPrompt: true });
  });
  it("handles timecodes", () => {
    expect(parseTimeWindow("between 1:00 and 2:30", scope)).toMatchObject({ start: 60, end: 150 });
  });
  it("falls back to the scope", () => {
    expect(parseTimeWindow("how many cars", scope)).toMatchObject({ start: 0, end: 300, fromPrompt: false });
  });
});

describe("buildReply", () => {
  it("is deterministic", () => {
    const req = { question: "How many cars?", scope };
    expect(buildReply(req)).toEqual(buildReply(req));
  });
  it("mentions the video and a count", () => {
    expect(buildReply({ question: "How many cars?", scope }).text).toMatch(
      /\*\*\d+ cars\*\* in Test video/,
    );
  });
  it("returns stat, chart and timestamps for a count question", () => {
    const types = buildReply({ question: "How many cars?", scope }).blocks.map((b) => b.type);
    expect(types).toEqual(["stat", "chart", "timestamps"]);
  });
  it("adds a table when asked", () => {
    const types = buildReply({ question: "Show a table of cars", scope }).blocks.map((b) => b.type);
    expect(types).toContain("table");
  });
  it("chart buckets add up to the stat value", () => {
    const { blocks } = buildReply({ question: "How many cars?", scope });
    const stat = blocks.find((b) => b.type === "stat");
    const chart = blocks.find((b) => b.type === "chart");
    const total = chart?.type === "chart" ? chart.data.reduce((n, d) => n + d.value, 0) : -1;
    expect(total).toBe(stat?.type === "stat" ? stat.value : -2);
  });
});

describe("histogram", () => {
  it("keeps bars at 12 or fewer", () => {
    expect(Math.ceil(300 / bucketSize(300))).toBeLessThanOrEqual(12);
    expect(histogram([1, 2, 299], 0, 300).reduce((n, b) => n + b.value, 0)).toBe(3);
  });
});
