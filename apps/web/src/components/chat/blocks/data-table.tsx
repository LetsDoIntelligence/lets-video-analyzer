"use client";

import { TimeChip } from "@/components/chat/blocks/time-chip";
import { useSeek } from "@/hooks/use-seek";
import type { ReplyBlock } from "@/lib/chat";
import { cn } from "@/lib/utils";

type TableBlock = Extract<ReplyBlock, { type: "table" }>;

export function DataTable({ block, videoId }: { block: TableBlock; videoId?: string }) {
  const { canSeek, seek } = useSeek(videoId);

  function cell(kind: TableBlock["columns"][number]["kind"], value: string | number) {
    if (kind === "time" && typeof value === "number") {
      return <TimeChip time={value} onSeek={seek} disabled={!canSeek} />;
    }
    if (kind === "percent" && typeof value === "number") return `${Math.round(value * 100)}%`;
    return value;
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface-2">
      {block.title && (
        <p className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">{block.title}</p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs tracking-wider text-ink-3 uppercase">
              {block.columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  className={cn(
                    "px-4 py-2.5 font-medium",
                    (c.kind === "number" || c.kind === "percent") && "text-right",
                  )}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, i) => (
              <tr key={i} className="border-t border-line transition-colors hover:bg-accent-soft">
                {block.columns.map((c) => (
                  <td
                    key={c.key}
                    className={cn(
                      "px-4 py-2 text-ink-2",
                      (c.kind === "number" || c.kind === "percent") && "text-right font-mono tabular-nums",
                    )}
                  >
                    {cell(c.kind, row[c.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
