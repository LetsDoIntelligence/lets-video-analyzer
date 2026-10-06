import { z } from "zod";
import { env } from "@/lib/env";
import type { VideoItem } from "@/lib/videos";

/** Failure from the video endpoints, with a message safe to show to the user. */
export class VideoApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "VideoApiError";
  }
}

const apiVideoSchema = z.object({
  id: z.string(),
  name: z.string(),
  sizeBytes: z.number(),
  durationSec: z.number().nullable().optional(),
  src: z.string(),
  thumbnailSrc: z.string().nullable().optional(),
});

export type ApiVideo = z.infer<typeof apiVideoSchema>;

/** Map a backend video to the UI's model, making media URLs absolute. */
export function toVideoItem(v: ApiVideo, baseUrl: string): VideoItem {
  return {
    id: v.id,
    name: v.name,
    source: "upload",
    src: `${baseUrl}${v.src}`,
    thumbnailSrc: v.thumbnailSrc ? `${baseUrl}${v.thumbnailSrc}` : undefined,
    durationSec: v.durationSec ?? undefined,
    sizeBytes: v.sizeBytes,
  };
}

/** FastAPI errors are `{detail: string}` (or a list for validation errors). */
async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await res.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  } catch {
    /* not JSON */
  }
  return fallback;
}

export interface VideosClient {
  list(): Promise<VideoItem[]>;
  upload(file: File, onProgress?: (fraction: number) => void): Promise<VideoItem>;
  remove(id: string): Promise<void>;
}

export function createVideosClient(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
  xhrFactory: () => XMLHttpRequest = () => new XMLHttpRequest(),
): VideosClient {
  const network = () => new VideoApiError("Couldn't reach the server. Is the API running?");

  return {
    async list() {
      let res: Response;
      try {
        res = await fetchImpl(`${baseUrl}/v1/videos`);
      } catch {
        throw network();
      }
      if (!res.ok) throw new VideoApiError("Couldn't load your videos.", res.status);
      const items = z.array(apiVideoSchema).parse(await res.json());
      return items.map((v) => toVideoItem(v, baseUrl));
    },

    // XHR rather than fetch: fetch can't report upload progress.
    upload(file, onProgress) {
      return new Promise<VideoItem>((resolve, reject) => {
        const xhr = xhrFactory();
        xhr.open("POST", `${baseUrl}/v1/videos`);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress?.(e.loaded / e.total);
        };
        xhr.onerror = () => reject(network());
        xhr.onload = () => {
          let body: unknown;
          try {
            body = JSON.parse(xhr.responseText);
          } catch {
            body = undefined;
          }
          if (xhr.status >= 200 && xhr.status < 300) {
            const parsed = apiVideoSchema.safeParse(body);
            if (parsed.success) return resolve(toVideoItem(parsed.data, baseUrl));
            return reject(new VideoApiError("The server sent an unexpected response."));
          }
          const detail = (body as { detail?: unknown } | undefined)?.detail;
          reject(
            new VideoApiError(
              typeof detail === "string" ? detail : "The upload failed.",
              xhr.status,
            ),
          );
        };
        const form = new FormData();
        form.append("file", file);
        xhr.send(form);
      });
    },

    async remove(id) {
      let res: Response;
      try {
        res = await fetchImpl(`${baseUrl}/v1/videos/${encodeURIComponent(id)}`, { method: "DELETE" });
      } catch {
        throw network();
      }
      // 404 means it's already gone, which is what the caller wanted.
      if (!res.ok && res.status !== 404) {
        throw new VideoApiError(await errorMessage(res, "Couldn't remove the video."), res.status);
      }
    },
  };
}

export const videosClient = createVideosClient(env.apiUrl);
