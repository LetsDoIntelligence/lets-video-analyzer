"use client";

import { useCallback } from "react";
import { useAnalysisStore } from "@/store/analysis-store";
import { useUiStore } from "@/store/ui-store";
import { useVideoStore } from "@/store/video-store";

/**
 * Lets reply blocks jump the player to a timestamp. Only enabled while the
 * video the answer was about is the one currently loaded.
 */
export function useSeek(videoId?: string) {
  const selectedId = useVideoStore((s) => s.selectedId);
  const seekTo = useAnalysisStore((s) => s.seekTo);
  const canSeek = Boolean(videoId) && selectedId === videoId;

  const seek = useCallback(
    (t: number) => {
      if (!canSeek) return;
      useUiStore.getState().setVideoCollapsed(false);
      seekTo(t);
      document.getElementById("video-heading")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    },
    [canSeek, seekTo],
  );

  return { canSeek, seek };
}
