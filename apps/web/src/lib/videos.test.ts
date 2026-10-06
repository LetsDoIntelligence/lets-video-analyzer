import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, validateVideoFile } from "./videos";

describe("formatDuration", () => {
  it("formats minutes and hours", () => {
    expect(formatDuration(5)).toBe("0:05");
    expect(formatDuration(185)).toBe("3:05");
    expect(formatDuration(3725)).toBe("1:02:05");
  });
});

describe("formatBytes", () => {
  it("scales units", () => {
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});

describe("validateVideoFile", () => {
  it("rejects non-video files", () => {
    expect(validateVideoFile(new File(["x"], "a.txt", { type: "text/plain" }))).toMatch(/isn't a video/);
  });
  it("accepts video files", () => {
    expect(validateVideoFile(new File(["x"], "a.mp4", { type: "video/mp4" }))).toBeNull();
  });
});
