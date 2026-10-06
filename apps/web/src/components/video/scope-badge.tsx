"use client";

import { Badge } from "@/components/ui/badge";
import { describeRange, isFullRange } from "@/lib/range";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";
import { useAnalysisStore } from "@/store/analysis-store";

/** Shows the time window that questions will be answered against. */
export function ScopeBadge() {
  const video = useVideoStore(selectSelectedVideo);
  const range = useAnalysisStore((s) => (video ? s.ranges[video.id] : undefined));
  const duration = video?.durationSec ?? 0;
  if (!video || duration < 2) return null;

  const effective = range ?? { start: 0, end: duration };
  const active = !isFullRange(effective, duration);
  return (
    <Badge tone={active ? "accent" : "neutral"} id="scope-badge">
      Scope · {describeRange(effective, duration)}
    </Badge>
  );
}
