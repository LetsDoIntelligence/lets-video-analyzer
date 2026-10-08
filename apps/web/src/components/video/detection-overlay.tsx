"use client";

import { useEffect, useRef, useState } from "react";
import { videosClient, type Detections } from "@/lib/api/videos-client";
import { CHUNK, boxesAt, chunkOf, containRect, type OverlayTrack } from "@/lib/overlay";

const COLORS: Record<string, string> = {
  car: "#4ade80",
  truck: "#fbbf24",
  bus: "#f97316",
  motorcycle: "#f472b6",
  bicycle: "#a78bfa",
  person: "#38bdf8",
};

/**
 * Draws the tracked boxes over the video. Fetches the detections in short windows around the
 * playhead (and the next one ahead of it) and keeps them, so playback never waits on the network.
 */
export function DetectionOverlay({
  videoId,
  currentTime,
  duration,
}: {
  videoId: string;
  currentTime: number;
  duration: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [chunks, setChunks] = useState<Record<number, Detections>>({});
  const requested = useRef(new Set<number>());

  const here = chunkOf(currentTime);

  // Load the current window and the one after it.
  useEffect(() => {
    const last = duration > 0 ? chunkOf(duration) : here + 1;
    for (const n of [here, here + 1]) {
      if (n > last || requested.current.has(n)) continue;
      requested.current.add(n);
      videosClient
        .getDetections(videoId, n * CHUNK, (n + 1) * CHUNK)
        .then((d) => setChunks((c) => ({ ...c, [n]: d })))
        .catch(() => requested.current.delete(n)); // retried on the next playhead move
    }
  }, [videoId, here, duration]);

  // Redraw whenever the playhead moves.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(rect.width * dpr);
    const h = Math.round(rect.height * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);

    const data = chunks[here];
    if (!data) return;
    // Tracks that straddle a window edge appear in both windows; use both so they don't flicker.
    const tracks = new Map<number, OverlayTrack>();
    for (const n of [here - 1, here, here + 1]) {
      for (const tr of chunks[n]?.tracks ?? []) {
        const known = tracks.get(tr.id);
        if (known) known.points = [...known.points, ...tr.points].sort((a, b) => a[0] - b[0]);
        else tracks.set(tr.id, { ...tr, points: [...tr.points] });
      }
    }
    const fit = containRect(rect.width, rect.height, data.width, data.height);
    const sx = fit.w / data.width;
    const sy = fit.h / data.height;

    ctx.lineWidth = 2;
    ctx.font = "600 11px var(--font-dm-sans), system-ui, sans-serif";
    ctx.textBaseline = "middle";
    for (const b of boxesAt([...tracks.values()], currentTime)) {
      const color = COLORS[b.cls] ?? "#e2e8f0";
      const x = fit.x + b.x1 * sx;
      const y = fit.y + b.y1 * sy;
      const bw = (b.x2 - b.x1) * sx;
      const bh = (b.y2 - b.y1) * sy;
      ctx.strokeStyle = color;
      ctx.strokeRect(x, y, bw, bh);
      const label = `${b.cls} #${b.id}`;
      const tw = ctx.measureText(label).width + 8;
      const ly = Math.max(fit.y, y - 16);
      ctx.fillStyle = color;
      ctx.fillRect(x, ly, tw, 16);
      ctx.fillStyle = "#04121a";
      ctx.fillText(label, x + 4, ly + 8.5);
    }
  }, [chunks, here, currentTime]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 size-full"
      data-testid="detection-overlay"
    />
  );
}
