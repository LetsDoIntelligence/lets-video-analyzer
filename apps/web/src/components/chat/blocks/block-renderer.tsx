"use client";

import { DataTable } from "@/components/chat/blocks/data-table";
import { StatCard } from "@/components/chat/blocks/stat-card";
import { TimeChip } from "@/components/chat/blocks/time-chip";
import { TimelineChart } from "@/components/chat/blocks/timeline-chart";
import { useSeek } from "@/hooks/use-seek";
import type { ReplyBlock } from "@/lib/chat";

function TimestampRow({
  block,
  videoId,
}: {
  block: Extract<ReplyBlock, { type: "timestamps" }>;
  videoId?: string;
}) {
  const { canSeek, seek } = useSeek(videoId);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-ink-3">{block.label}</span>
      {block.times.map((t) => (
        <TimeChip key={t} time={t} onSeek={seek} disabled={!canSeek} />
      ))}
    </div>
  );
}

/** Renders the structured parts of an assistant answer. */
export function BlockRenderer({ blocks, videoId }: { blocks: ReplyBlock[]; videoId?: string }) {
  return (
    <div className="mt-4 flex flex-col gap-3">
      {blocks.map((block, i) => (
        <div key={i} className="animate-rise" style={{ animationDelay: `${i * 90}ms` }}>
          {block.type === "stat" && (
            <StatCard label={block.label} value={block.value} caption={block.caption} />
          )}
          {block.type === "chart" && <TimelineChart block={block} videoId={videoId} />}
          {block.type === "table" && <DataTable block={block} videoId={videoId} />}
          {block.type === "timestamps" && <TimestampRow block={block} videoId={videoId} />}
        </div>
      ))}
    </div>
  );
}
