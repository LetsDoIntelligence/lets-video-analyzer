"use client";

import { useRef, type RefObject } from "react";
import { cn } from "@/lib/utils";
import { formatTimecode, type TimeRange } from "@/lib/range";

interface Props {
  duration: number;
  currentTime: number;
  range: TimeRange;
  rangeActive: boolean;
  onSeek: (t: number) => void;
  onStartChange: (t: number) => void;
  onEndChange: (t: number) => void;
}

function timeFromPointer(track: HTMLElement | null, clientX: number, duration: number) {
  const rect = track?.getBoundingClientRect();
  if (!rect || rect.width === 0) return 0;
  return Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1) * duration;
}

interface HandleProps {
  kind: "start" | "end";
  trackRef: RefObject<HTMLDivElement | null>;
  duration: number;
  value: number;
  leftPct: number;
  disabled: boolean;
  onChange: (t: number) => void;
}

function RangeHandle({ kind, trackRef, duration, value, leftPct, disabled, onChange }: HandleProps) {
  return (
    <div
      role="slider"
      tabIndex={disabled ? -1 : 0}
      aria-label={kind === "start" ? "Range start" : "Range end"}
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(value)}
      aria-valuetext={formatTimecode(value)}
      onPointerDown={(e) => {
        if (disabled) return;
        e.stopPropagation();
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          onChange(timeFromPointer(trackRef.current, e.clientX, duration));
        }
      }}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 10 : 1;
        if (e.key === "ArrowLeft" || e.key === "ArrowDown") onChange(value - step);
        else if (e.key === "ArrowRight" || e.key === "ArrowUp") onChange(value + step);
        else return;
        e.preventDefault();
        e.stopPropagation();
      }}
      className="group absolute top-1/2 z-10 flex h-8 w-4 cursor-ew-resize touch-none items-center justify-center focus-visible:outline-none"
      style={{ left: `${leftPct}%`, translate: kind === "start" ? "-100% -50%" : "0 -50%" }}
    >
      <span className="h-6 w-1.5 rounded-full bg-accent shadow-sm transition-all group-hover:h-7 group-focus-visible:h-7 group-focus-visible:ring-2 group-focus-visible:ring-ink" />
    </div>
  );
}

/**
 * Seek bar with a selectable analysis window. Drag the track to scrub,
 * drag the two handles (or use arrow keys) to set the window.
 */
export function RangeTimeline({
  duration,
  currentTime,
  range,
  rangeActive,
  onSeek,
  onStartChange,
  onEndChange,
}: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  const disabled = duration <= 0;
  const pct = (t: number) => (duration > 0 ? (t / duration) * 100 : 0);

  return (
    <div
      ref={trackRef}
      onPointerDown={(e) => {
        if (disabled) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        onSeek(timeFromPointer(trackRef.current, e.clientX, duration));
      }}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          onSeek(timeFromPointer(trackRef.current, e.clientX, duration));
        }
      }}
      className={cn(
        "relative h-9 w-full touch-none select-none",
        disabled ? "opacity-50" : "cursor-pointer",
      )}
    >
      <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-surface-3" />

      <div
        className={cn(
          "absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full transition-colors",
          rangeActive ? "bg-accent/60" : "bg-ink-3/40",
        )}
        style={{ left: `${pct(range.start)}%`, width: `${pct(range.end) - pct(range.start)}%` }}
      />

      <div
        className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-l-full bg-ink/80"
        style={{ left: 0, width: `${pct(currentTime)}%` }}
      />

      <div
        className="pointer-events-none absolute top-1/2 z-20 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-canvas bg-ink shadow"
        style={{ left: `${pct(currentTime)}%` }}
      />

      <RangeHandle
        kind="start"
        trackRef={trackRef}
        duration={duration}
        value={range.start}
        leftPct={pct(range.start)}
        disabled={disabled}
        onChange={onStartChange}
      />
      <RangeHandle
        kind="end"
        trackRef={trackRef}
        duration={duration}
        value={range.end}
        leftPct={pct(range.end)}
        disabled={disabled}
        onChange={onEndChange}
      />
    </div>
  );
}
