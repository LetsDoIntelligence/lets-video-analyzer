import { env } from "@/lib/env";
import { analyze as mockAnalyze } from "@/lib/mock-analyzer";
import {
  analyzeEventSchema,
  analyzeRequestSchema,
  type AnalyzeEvent,
  type AnalyzeRequest,
} from "@/lib/api/schemas";
import { readSse } from "@/lib/api/sse";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Everything the UI needs from the analysis backend. */
export interface AnalyzerClient {
  analyze(req: AnalyzeRequest, signal: AbortSignal): AsyncGenerator<AnalyzeEvent>;
}

/** In-browser fake used until the real backend exists. Output is still schema-checked. */
export const mockClient: AnalyzerClient = {
  async *analyze(req, signal) {
    const request = analyzeRequestSchema.parse(req);
    for await (const event of mockAnalyze(request, signal)) {
      yield analyzeEventSchema.parse(event);
    }
  },
};

/** Talks to the FastAPI backend: POST /v1/analyze, answered as an SSE stream. */
export function createHttpClient(baseUrl: string, fetchImpl: typeof fetch = fetch): AnalyzerClient {
  return {
    async *analyze(req, signal) {
      const body = analyzeRequestSchema.parse(req);

      let res: Response;
      try {
        res = await fetchImpl(`${baseUrl}/v1/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify(body),
          signal,
        });
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") throw e;
        throw new ApiError("Couldn't reach the analysis service.");
      }

      if (!res.ok || !res.body) {
        throw new ApiError(`The analysis service returned an error (${res.status}).`, res.status);
      }

      for await (const data of readSse(res.body)) {
        let parsed: unknown;
        try {
          parsed = JSON.parse(data);
        } catch {
          throw new ApiError("The analysis service sent an unreadable response.");
        }
        const result = analyzeEventSchema.safeParse(parsed);
        if (!result.success) throw new ApiError("The analysis service sent an unexpected response.");
        yield result.data;
      }
    },
  };
}

export function getAnalyzerClient(): AnalyzerClient {
  return env.useMocks ? mockClient : createHttpClient(env.apiUrl);
}
