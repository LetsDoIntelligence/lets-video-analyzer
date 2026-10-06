"use client";

import { useEffect, useState } from "react";

function useCountUp(target: number, durationMs = 900) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ms = reduced ? 0 : durationMs;
    const startedAt = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const p = ms === 0 ? 1 : Math.min((now - startedAt) / ms, 1);
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs]);

  return value;
}

/** Big headline number with a gentle count-up. */
export function StatCard({
  label,
  value,
  caption,
}: {
  label: string;
  value: number;
  caption?: string;
}) {
  const shown = useCountUp(value);
  return (
    <div className="flex items-end justify-between gap-4 rounded-2xl border border-line bg-surface-2 px-5 py-4">
      <div className="min-w-0">
        <p className="truncate text-xs font-medium tracking-wider text-ink-3 uppercase">{label}</p>
        <p
          className="font-display mt-1 text-6xl leading-none font-semibold tracking-tight text-accent tabular-nums"
          aria-label={`${value} ${label}`}
        >
          {shown}
        </p>
      </div>
      {caption && <p className="pb-1 text-right text-xs text-ink-3">{caption}</p>}
    </div>
  );
}
