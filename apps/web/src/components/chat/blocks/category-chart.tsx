"use client";

import { Bar, BarChart, Cell, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ReplyBlock } from "@/lib/chat";

type CategoriesBlock = Extract<ReplyBlock, { type: "categories" }>;

/** Bar colors for the color names the analyzer can report; anything else uses the accent. */
const SWATCH: Record<string, string> = {
  white: "#e2e8f0",
  black: "#334155",
  gray: "#94a3b8",
  red: "#ef4444",
  orange: "#f97316",
  yellow: "#facc15",
  green: "#22c55e",
  blue: "#3b82f6",
  unknown: "#64748b",
};

function CategoryTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: CategoriesBlock["data"][number] }[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-xl border border-line-strong bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold capitalize text-ink">{d.label}</p>
      <p className="mt-0.5 text-ink-3">{d.value} detected</p>
    </div>
  );
}

/** Counts per category, e.g. how many cars of each color. */
export function CategoryChart({ block }: { block: CategoriesBlock }) {
  return (
    <figure className="rounded-2xl border border-line bg-surface-2 p-4">
      <figcaption className="mb-3 text-sm font-semibold text-ink">{block.title}</figcaption>
      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart data={block.data} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
              interval={0}
            />
            <YAxis
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
            />
            <Tooltip content={<CategoryTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
            <Bar
              dataKey="value"
              radius={[6, 6, 0, 0]}
              maxBarSize={44}
              isAnimationActive
              animationDuration={700}
            >
              {block.data.map((d) => (
                <Cell key={d.label} fill={SWATCH[d.label] ?? "var(--accent)"} stroke="var(--line-strong)" />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
