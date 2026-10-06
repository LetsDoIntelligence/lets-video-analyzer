import { z } from "zod";

export const videoItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().optional(),
  source: z.enum(["sample", "upload"]),
  /** Playable URL. Samples have none until footage is supplied. */
  src: z.string().optional(),
  thumbnailSrc: z.string().optional(),
  durationSec: z.number().nonnegative().optional(),
  sizeBytes: z.number().nonnegative().optional(),
});

export type VideoItem = z.infer<typeof videoItemSchema>;

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024; // 2 GB

/** Placeholder library until real footage arrives. Add `src: "/samples/x.mp4"` to enable playback. */
export const SAMPLE_VIDEOS: VideoItem[] = [
  {
    id: "sample-1",
    name: "Synthetic traffic",
    description: "Test clip, not real footage",
    source: "sample",
    src: "/samples/synthetic-traffic.mp4",
    durationSec: 60,
  },
  {
    id: "sample-2",
    name: "City intersection",
    description: "Cars, people, trucks",
    source: "sample",
    durationSec: 480,
  },
  {
    id: "sample-3",
    name: "Construction site",
    description: "Helmet compliance",
    source: "sample",
    durationSec: 360,
  },
  {
    id: "sample-4",
    name: "Park and grounds",
    description: "Open-vocabulary objects",
    source: "sample",
    durationSec: 240,
  },
];

export function validateVideoFile(file: File): string | null {
  if (!file.type.startsWith("video/")) return "That file isn't a video.";
  if (file.size > MAX_UPLOAD_BYTES) return "Videos are limited to 2 GB.";
  return null;
}

export function formatDuration(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0");
  const ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

/** Read duration from the file's metadata in the browser. */
export function readVideoDuration(url: string): Promise<number | undefined> {
  return new Promise((resolve) => {
    const el = document.createElement("video");
    el.preload = "metadata";
    el.onloadedmetadata = () => resolve(Number.isFinite(el.duration) ? el.duration : undefined);
    el.onerror = () => resolve(undefined);
    el.src = url;
  });
}
