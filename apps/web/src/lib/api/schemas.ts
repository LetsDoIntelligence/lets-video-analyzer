import { z } from "zod";

/**
 * Single source of truth for the analyzer API contract.
 * The FastAPI backend (Phase 2+) mirrors these shapes; see docs/api-contract.md.
 */

export const scopeInfoSchema = z.object({
  videoId: z.string().min(1),
  videoName: z.string(),
  /** Analysis window in seconds. */
  start: z.number().nonnegative(),
  end: z.number().nonnegative(),
  duration: z.number().nonnegative(),
  /** Human label, e.g. "3:00 – 6:00" or "Entire video". */
  label: z.string(),
});

export const replyBlockSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("stat"),
    label: z.string(),
    value: z.number(),
    caption: z.string().optional(),
  }),
  z.object({
    type: z.literal("chart"),
    title: z.string(),
    /** One bar per time bucket; `start` is the bucket start in seconds. */
    data: z.array(z.object({ label: z.string(), start: z.number(), value: z.number() })),
  }),
  z.object({
    type: z.literal("table"),
    title: z.string().optional(),
    columns: z.array(
      z.object({
        key: z.string(),
        label: z.string(),
        kind: z.enum(["text", "number", "time", "percent"]).optional(),
      }),
    ),
    rows: z.array(z.record(z.string(), z.union([z.string(), z.number()]))),
  }),
  z.object({
    type: z.literal("timestamps"),
    label: z.string(),
    times: z.array(z.number()),
  }),
]);

export const messageStatusSchema = z.enum(["streaming", "done", "error", "stopped"]);

export const chatMessageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]),
  text: z.string(),
  /** Rich content shown under the text once the answer is complete. */
  blocks: z.array(replyBlockSchema).optional(),
  status: messageStatusSchema,
  /** What the question was asked against. */
  scope: scopeInfoSchema.optional(),
  /** Human-readable failure reason, when status is "error". */
  error: z.string().optional(),
  createdAt: z.number(),
});

export const analyzeRequestSchema = z.object({
  question: z.string().trim().min(1, "Ask a question first.").max(1000, "Questions are limited to 1000 characters."),
  scope: scopeInfoSchema,
});

/** Events streamed (as SSE) by POST /v1/analyze. */
export const analyzeEventSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("text"), chunk: z.string() }),
  z.object({ type: z.literal("blocks"), blocks: z.array(replyBlockSchema) }),
  z.object({ type: z.literal("error"), message: z.string() }),
]);

export type ScopeInfo = z.infer<typeof scopeInfoSchema>;
export type ReplyBlock = z.infer<typeof replyBlockSchema>;
export type MessageStatus = z.infer<typeof messageStatusSchema>;
export type ChatMessage = z.infer<typeof chatMessageSchema>;
export type AnalyzeRequest = z.infer<typeof analyzeRequestSchema>;
export type AnalyzeEvent = z.infer<typeof analyzeEventSchema>;
