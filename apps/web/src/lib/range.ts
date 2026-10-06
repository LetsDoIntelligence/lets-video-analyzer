import { formatDuration } from "@/lib/videos";

export interface TimeRange {
  start: number;
  end: number;
}

/** Smallest analysable window, in seconds. */
export const MIN_RANGE_SEC = 1;

const clamp = (n: number, lo: number, hi: number) => Math.min(Math.max(n, lo), hi);

/**
 * Parse "95", "95s", "1:35" or "1:02:05" into seconds. Returns null if invalid.
 */
export function parseTimecode(input: string): number | null {
  const text = input.trim().toLowerCase().replace(/s$/, "");
  if (!text) return null;
  const parts = text.split(":");
  if (parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$/.test(p))) return null;
  return parts.reduce((acc, p) => acc * 60 + Number(p), 0);
}

export const formatTimecode = formatDuration;

export function withStart(range: TimeRange, t: number): TimeRange {
  return { start: clamp(t, 0, range.end - MIN_RANGE_SEC), end: range.end };
}

export function withEnd(range: TimeRange, t: number, duration: number): TimeRange {
  return { start: range.start, end: clamp(t, range.start + MIN_RANGE_SEC, duration) };
}

/** True when the range covers (almost) the whole video. */
export function isFullRange(range: TimeRange, duration: number): boolean {
  return range.start <= 0.05 && range.end >= duration - 0.05;
}

/** Human description used in chat context, e.g. "3:00 – 6:00". */
export function describeRange(range: TimeRange, duration: number): string {
  return isFullRange(range, duration)
    ? "Entire video"
    : `${formatTimecode(range.start)} – ${formatTimecode(range.end)}`;
}
