"use client";

import { Loader2, RefreshCw } from "lucide-react";
import { useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { isIndexing } from "@/lib/api/videos-client";
import { env } from "@/lib/env";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";

const POLL_MS = 1000;
const RETRY_MS = 3000;

const iconButton =
  "flex size-6 cursor-pointer items-center justify-center rounded-full text-ink-3 transition-colors hover:bg-accent-soft hover:text-ink";

/**
 * Shows whether the selected upload has been analysed yet (objects detected and tracked by the
 * backend), and lets you re-run it. Polls while the server is still working.
 */
export function IndexBadge() {
  const video = useVideoStore(selectSelectedVideo);
  const id = video?.source === "upload" ? video.id : null;
  const status = useVideoStore((s) => (id ? s.indexes[id] : undefined));
  const refreshIndex = useVideoStore((s) => s.refreshIndex);
  const reindex = useVideoStore((s) => s.reindex);
  const active = isIndexing(status);

  useEffect(() => {
    if (!id || env.useMocks) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      const latest = await refreshIndex(id);
      if (stopped) return;
      if (latest === null) timer = setTimeout(() => void tick(), RETRY_MS);
      else if (isIndexing(latest)) timer = setTimeout(() => void tick(), POLL_MS);
    };
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
    // Re-run when polling should (re)start, e.g. after "Re-analyze".
  }, [id, active, refreshIndex]);

  if (!id || env.useMocks || !status) return null;

  if (active) {
    const pct = Math.round(status.progress * 100);
    return (
      <Badge tone="accent" id="index-badge" role="status" aria-live="polite">
        <Loader2 className="size-3 animate-spin" aria-hidden />
        {status.state === "queued" ? "Queued" : `Analyzing ${pct}%`}
      </Badge>
    );
  }

  const rerun = (label: string) => (
    <button
      type="button"
      id="index-rerun"
      onClick={() => void reindex(id)}
      aria-label={label}
      title={label}
      className={iconButton}
    >
      <RefreshCw className="size-3.5" />
    </button>
  );

  if (status.state === "ready") {
    return (
      <span className="flex items-center gap-1">
        <Badge tone="positive" id="index-badge" role="status">
          Analyzed · {status.nTracks ?? 0} {status.nTracks === 1 ? "object" : "objects"}
        </Badge>
        {rerun("Re-analyze video")}
      </span>
    );
  }

  if (status.state === "failed") {
    return (
      <span className="flex items-center gap-1">
        <Badge tone="danger" id="index-badge" role="status" title={status.error ?? undefined}>
          Analysis failed
        </Badge>
        {rerun("Retry analysis")}
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1">
      <Badge tone="neutral" id="index-badge" role="status">
        Not analyzed
      </Badge>
      {rerun("Analyze video")}
    </span>
  );
}
