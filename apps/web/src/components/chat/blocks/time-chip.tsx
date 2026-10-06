"use client";

import { Clock } from "lucide-react";
import { formatTimecode } from "@/lib/range";
import { cn } from "@/lib/utils";

/** A clickable timestamp that jumps the video player. */
export function TimeChip({
  time,
  onSeek,
  disabled,
  className,
}: {
  time: number;
  onSeek: (t: number) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onSeek(time)}
      title={disabled ? "Select this video to jump to the moment" : "Jump to this moment"}
      className={cn(
        "inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 font-mono text-xs text-ink-2 tabular-nums transition-all duration-300 hover:border-accent hover:bg-accent-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-line disabled:hover:bg-surface-2",
        className,
      )}
    >
      <Clock className="size-3" />
      {formatTimecode(time)}
    </button>
  );
}
