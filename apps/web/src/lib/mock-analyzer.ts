import { formatTimecode, parseTimecode } from "@/lib/range";
import type { AnalyzeEvent, AnalyzeRequest, ReplyBlock, ScopeInfo } from "@/lib/chat";

/**
 * MOCK analyser used while the detection backend doesn't exist (Phases 2-5).
 * Counts are deterministic fakes derived from the question + scope.
 */

interface Subject {
  singular: string;
  plural: string;
  /** Rough fake detections per minute. */
  perMinute: number;
}

const SUBJECTS: [RegExp, Subject][] = [
  [/\b(trucks?|lorr(?:y|ies))\b/, { singular: "truck", plural: "trucks", perMinute: 2 }],
  [/\b(people|persons?|pedestrians?|workers?)\b/, { singular: "person", plural: "people", perMinute: 6 }],
  [/\btrees?\b/, { singular: "tree", plural: "trees", perMinute: 0.5 }],
  [/\bcars?\b/, { singular: "car", plural: "cars", perMinute: 9 }],
];

const COLORS = ["red", "blue", "white", "black", "yellow", "green", "silver", "grey", "gray"];

export interface ParsedPrompt {
  subject: Subject;
  color?: string;
  helmets: boolean;
}

export function parsePrompt(question: string): ParsedPrompt {
  const q = question.toLowerCase();
  const subject = SUBJECTS.find(([re]) => re.test(q))?.[1] ?? SUBJECTS[3][1];
  const color = COLORS.find((c) => new RegExp(`\\b${c}\\b`).test(q));
  return { subject, color, helmets: /\bhelmets?\b/.test(q) };
}

const UNIT = String.raw`(sec(?:ond)?s?|s|min(?:ute)?s?|m)`;

function unitSeconds(unit?: string): number | undefined {
  if (!unit) return undefined;
  return unit.startsWith("m") ? 60 : 1;
}

export interface Window {
  start: number;
  end: number;
  fromPrompt: boolean;
}

/** Understands "first 30 sec", "from 3 to 6 minutes", "between 3:00 and 6:00". */
export function parseTimeWindow(question: string, scope: ScopeInfo): Window {
  const q = question.toLowerCase();
  const fallback: Window = { start: scope.start, end: scope.end, fromPrompt: false };

  const first = q.match(new RegExp(String.raw`first\s+(\d+(?:\.\d+)?)\s*${UNIT}\b`));
  if (first) {
    const len = Number(first[1]) * (unitSeconds(first[2]) ?? 1);
    const end = Math.min(scope.start + len, scope.end);
    return end > scope.start ? { start: scope.start, end, fromPrompt: true } : fallback;
  }

  const between = q.match(
    new RegExp(
      String.raw`(?:between|from)\s+(\d+(?::\d+)?)\s*(?:and|to|-)\s*(\d+(?::\d+)?)\s*${UNIT}?(?![a-z])`,
    ),
  );
  if (between) {
    const unit = unitSeconds(between[3]);
    const toSeconds = (token: string) => {
      if (token.includes(":")) return parseTimecode(token);
      const n = Number(token);
      if (unit) return n * unit;
      // No unit: minutes if that fits inside the video, otherwise seconds.
      return n * 60 <= scope.duration ? n * 60 : n;
    };
    const a = toSeconds(between[1]);
    const b = toSeconds(between[2]);
    if (a !== null && b !== null && b > a) {
      const start = Math.max(0, a);
      const end = Math.min(scope.duration, b);
      if (end > start) return { start, end, fromPrompt: true };
    }
  }
  return fallback;
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const BUCKET_SIZES = [5, 10, 15, 30, 60, 120, 300];

/** Smallest bucket size that keeps the chart at 12 bars or fewer. */
export function bucketSize(lengthSec: number): number {
  return BUCKET_SIZES.find((b) => Math.ceil(lengthSec / b) <= 12) ?? 600;
}

export function histogram(times: number[], start: number, end: number) {
  const size = bucketSize(end - start);
  const n = Math.max(1, Math.ceil((end - start) / size));
  const buckets = Array.from({ length: n }, (_, i) => ({
    label: formatTimecode(start + i * size),
    start: start + i * size,
    value: 0,
  }));
  for (const t of times) {
    buckets[Math.min(n - 1, Math.floor((t - start) / size))].value++;
  }
  return buckets;
}

const wantsTable = (q: string) => /\b(table|list|breakdown|details?|each|show)\b/i.test(q);

export interface Reply {
  text: string;
  blocks: ReplyBlock[];
}

export function buildReply(req: AnalyzeRequest): Reply {
  const parsed = parsePrompt(req.question);
  const win = parseTimeWindow(req.question, req.scope);
  const length = Math.max(win.end - win.start, 1);
  const minutes = length / 60;

  const seed = hash(`${req.scope.videoId}|${parsed.subject.plural}|${parsed.color ?? ""}|${parsed.helmets}`);
  const jitter = 0.75 + (seed % 50) / 100; // 0.75 - 1.24
  let count = Math.round(parsed.subject.perMinute * minutes * jitter);
  if (parsed.color) count = Math.round(count * 0.25);
  if (parsed.helmets) count = Math.round(count * 0.4);

  const noun = count === 1 ? parsed.subject.singular : parsed.subject.plural;
  const descriptor = parsed.helmets
    ? `${parsed.subject.plural} wearing helmets`
    : `${parsed.color ? parsed.color + " " : ""}${noun}`;

  const span = `${formatTimecode(win.start)} – ${formatTimecode(win.end)}`;
  const where = win.fromPrompt || req.scope.label !== "Entire video" ? span : "the entire video";

  const text = [
    `I counted **${count} ${descriptor}** in ${req.scope.videoName} (${where}).`,
    "Demo mode: these numbers are simulated. Real detection is connected in a later phase.",
  ].join("\n\n");

  // Fake but stable detection timestamps inside the window.
  const rand = mulberry32(seed ^ Math.round(win.start * 1000) ^ Math.round(win.end * 1000));
  const times = Array.from({ length: count }, () => win.start + rand() * (win.end - win.start))
    .map((t) => Math.round(t * 10) / 10)
    .sort((a, b) => a - b);

  const blocks: ReplyBlock[] = [
    { type: "stat", label: descriptor, value: count, caption: `${span} · ${req.scope.videoName}` },
  ];

  if (length >= 20 && count >= 3) {
    blocks.push({
      type: "chart",
      title: `${parsed.subject.plural[0].toUpperCase()}${parsed.subject.plural.slice(1)} over time`,
      data: histogram(times, win.start, win.end),
    });
  }
  if (count >= 1) {
    blocks.push({ type: "timestamps", label: "Jump to first detections", times: times.slice(0, 6) });
  }
  if (count >= 1 && (wantsTable(req.question) || parsed.color || parsed.helmets)) {
    const label = parsed.helmets ? "person · helmet" : `${parsed.color ? parsed.color + " " : ""}${parsed.subject.singular}`;
    blocks.push({
      type: "table",
      title: `First detections (${Math.min(count, 8)} of ${count})`,
      columns: [
        { key: "n", label: "#", kind: "number" },
        { key: "time", label: "Time", kind: "time" },
        { key: "object", label: "Object" },
        { key: "confidence", label: "Confidence", kind: "percent" },
      ],
      rows: times.slice(0, 8).map((t, i) => ({
        n: i + 1,
        time: t,
        object: label,
        confidence: Math.round((0.8 + rand() * 0.19) * 100) / 100,
      })),
    });
  }

  return { text, blocks };
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const t = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });

/** Streams the reply word by word, then delivers the rich blocks. */
export async function* analyze(
  req: AnalyzeRequest,
  signal: AbortSignal,
  opts: { thinkMs?: number; tokenMs?: number } = {},
): AsyncGenerator<AnalyzeEvent> {
  const { thinkMs = 700, tokenMs = 30 } = opts;
  await sleep(thinkMs, signal);
  const reply = buildReply(req);
  const tokens = reply.text.match(/\S+\s*|\s+/g) ?? [];
  for (const token of tokens) {
    await sleep(tokenMs + Math.random() * 25, signal);
    yield { type: "text", chunk: token };
  }
  if (reply.blocks.length > 0) {
    await sleep(Math.min(tokenMs * 8, 300), signal);
    yield { type: "blocks", blocks: reply.blocks };
  }
}
