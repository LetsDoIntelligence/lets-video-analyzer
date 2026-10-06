"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSeek } from "@/hooks/use-seek";
import type { ReplyBlock } from "@/lib/chat";
import { formatTimecode } from "@/lib/range";

type ChartBlock = Extract<ReplyBlock, { type: "chart" }>;
type Datum = ChartBlock["data"][number];

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: Datum }[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-xl border border-line-strong bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="font-mono text-ink-3">from {formatTimecode(d.start)}</p>
      <p className="mt-0.5 font-semibold text-ink">{d.value} detected</p>
    </div>
  );
}

/** Detections per time bucket. Click a bar to jump the video to that moment. */
export function TimelineChart({
  block,
  videoId,
}: {
  block: ChartBlock;
  videoId?: string;
}) {
  const { canSeek, seek } = useSeek(videoId);

  return (
    <figure className="rounded-2xl border border-line bg-surface-2 p-4">
      <figcaption className="mb-3 flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-ink">{block.title}</span>
        <span className="text-xs text-ink-3">{canSeek ? "Click a bar to jump" : ""}</span>
      </figcaption>
      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart data={block.data} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
              interval="preserveStartEnd"
            />
            <YAxis
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
            <Bar
              dataKey="value"
              fill="var(--accent)"
              radius={[6, 6, 0, 0]}
              maxBarSize={36}
              cursor={canSeek ? "pointer" : "default"}
              isAnimationActive
              animationDuration={700}
              onClick={(d) => {
                const start = (d as unknown as Datum).start;
                if (typeof start === "number") seek(start);
              }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
