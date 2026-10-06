import { describe, expect, it } from "vitest";
import { ApiError, createHttpClient, mockClient } from "@/lib/api/client";
import { analyzeEventSchema, replyBlockSchema, type AnalyzeEvent } from "@/lib/api/schemas";

const scope = {
  videoId: "v1",
  videoName: "Clip",
  start: 0,
  end: 60,
  duration: 60,
  label: "Entire video",
};
const req = { question: "how many cars?", scope };

function sseResponse(chunks: string[], status = 200): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
  return new Response(body, { status });
}

async function collect(gen: AsyncGenerator<AnalyzeEvent>) {
  const out: AnalyzeEvent[] = [];
  for await (const e of gen) out.push(e);
  return out;
}

describe("schemas", () => {
  it("rejects unknown block types and bad events", () => {
    expect(replyBlockSchema.safeParse({ type: "nope" }).success).toBe(false);
    expect(analyzeEventSchema.safeParse({ type: "text" }).success).toBe(false);
    expect(analyzeEventSchema.safeParse({ type: "error", message: "x" }).success).toBe(true);
  });
});

describe("mockClient", () => {
  it("streams schema-valid events", async () => {
    const events = await collect(mockClient.analyze(req, new AbortController().signal));
    expect(events.some((e) => e.type === "text")).toBe(true);
  });
});

describe("createHttpClient", () => {
  it("parses SSE events split across chunks", async () => {
    const line = 'data: {"type":"text","chunk":"hello"}\n\n';
    const fake = (async () => sseResponse([line.slice(0, 10), line.slice(10)])) as typeof fetch;
    const events = await collect(
      createHttpClient("http://x", fake).analyze(req, new AbortController().signal),
    );
    expect(events).toEqual([{ type: "text", chunk: "hello" }]);
  });

  it("throws ApiError on non-OK status", async () => {
    const fake = (async () => sseResponse([], 500)) as typeof fetch;
    await expect(
      collect(createHttpClient("http://x", fake).analyze(req, new AbortController().signal)),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("throws ApiError on an invalid event", async () => {
    const fake = (async () => sseResponse(['data: {"type":"bogus"}\n\n'])) as typeof fetch;
    await expect(
      collect(createHttpClient("http://x", fake).analyze(req, new AbortController().signal)),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("throws ApiError when the network fails", async () => {
    const fake = (async () => {
      throw new TypeError("fail");
    }) as typeof fetch;
    await expect(
      collect(createHttpClient("http://x", fake).analyze(req, new AbortController().signal)),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
