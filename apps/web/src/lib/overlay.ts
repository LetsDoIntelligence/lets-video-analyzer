/** Detection boxes in source-video pixels, one sample per analysed frame. */
export interface OverlayTrack {
  id: number;
  cls: string;
  /** [t, x1, y1, x2, y2] */
  points: number[][];
}

export interface Box {
  id: number;
  cls: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/** Samples are ~0.2 s apart; a track not seen for longer than this is treated as gone. */
export const MAX_GAP = 0.6;

/** Where each track is at time `t`, interpolating between its two nearest samples. */
export function boxesAt(tracks: OverlayTrack[], t: number): Box[] {
  const out: Box[] = [];
  for (const tr of tracks) {
    const pts = tr.points;
    if (pts.length === 0) continue;
    // Index of the first sample at or after t.
    let lo = 0;
    let hi = pts.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (pts[mid][0] < t) lo = mid + 1;
      else hi = mid;
    }
    const next = pts[lo];
    const prev = pts[lo - 1];
    let b: number[] | null = null;
    if (prev && next) {
      const gap = next[0] - prev[0];
      if (gap > MAX_GAP) {
        const nearest = t - prev[0] <= next[0] - t ? prev : next;
        if (Math.abs(nearest[0] - t) <= MAX_GAP / 2) b = nearest;
      } else {
        const k = gap === 0 ? 0 : (t - prev[0]) / gap;
        b = prev.map((v, i) => v + (next[i] - v) * k);
      }
    } else {
      const only = next ?? prev;
      if (Math.abs(only[0] - t) <= MAX_GAP / 2) b = only;
    }
    if (b) out.push({ id: tr.id, cls: tr.cls, x1: b[1], y1: b[2], x2: b[3], y2: b[4] });
  }
  return out;
}

/** The rectangle the video's picture occupies inside an `object-contain` box. */
export function containRect(boxW: number, boxH: number, srcW: number, srcH: number) {
  if (!srcW || !srcH || !boxW || !boxH) return { x: 0, y: 0, w: boxW, h: boxH };
  const scale = Math.min(boxW / srcW, boxH / srcH);
  const w = srcW * scale;
  const h = srcH * scale;
  return { x: (boxW - w) / 2, y: (boxH - h) / 2, w, h };
}

/** Length of one fetched window, seconds (the API allows up to 120). */
export const CHUNK = 30;

export const chunkOf = (t: number) => Math.max(0, Math.floor(t / CHUNK));
