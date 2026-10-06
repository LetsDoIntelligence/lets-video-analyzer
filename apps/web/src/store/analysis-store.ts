import { create } from "zustand";
import type { TimeRange } from "@/lib/range";

/**
 * Analysis context shared between the player, the chat (T6) and reply
 * timestamp chips (T7): per-video time range, playhead and seek requests.
 */
interface AnalysisState {
  /** Selected analysis window per video id. Absent = entire video. */
  ranges: Record<string, TimeRange>;
  currentTime: number;
  seekRequest: { time: number; nonce: number } | null;
  setRange: (videoId: string, range: TimeRange | null) => void;
  setCurrentTime: (t: number) => void;
  /** Ask the player to jump to a timestamp (used by reply chips). */
  seekTo: (t: number) => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  ranges: {},
  currentTime: 0,
  seekRequest: null,

  setRange: (videoId, range) =>
    set((s) => {
      const next = { ...s.ranges };
      if (range) next[videoId] = range;
      else delete next[videoId];
      return { ranges: next };
    }),

  setCurrentTime: (currentTime) => set({ currentTime }),

  seekTo: (time) => set({ seekRequest: { time, nonce: Date.now() + Math.random() } }),
}));
