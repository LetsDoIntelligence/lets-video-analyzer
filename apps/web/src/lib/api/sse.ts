/**
 * Minimal Server-Sent Events parsing for fetch() response bodies.
 */

/** Split a text buffer into complete SSE `data` payloads plus any unfinished remainder. */
export function parseSseBuffer(buffer: string): { events: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: string[] = [];
  for (const part of parts) {
    const data = part
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (data) events.push(data);
  }
  return { events, rest };
}

/** Yield each SSE `data` payload from a streaming response body. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSseBuffer(buffer);
      buffer = rest;
      yield* events;
    }
    buffer += decoder.decode();
    // Flush a final event that wasn't terminated by a blank line.
    const { events } = parseSseBuffer(`${buffer}\n\n`);
    yield* events;
  } finally {
    reader.releaseLock();
  }
}
