"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { formatTimecode, parseTimecode } from "@/lib/range";

interface Props {
  id: string;
  label: string;
  value: number;
  disabled?: boolean;
  onCommit: (t: number) => void;
}

/** Small mm:ss input that commits on Enter/blur and reverts on invalid input. */
export function TimeField({ id, label, value, disabled, onCommit }: Props) {
  const [draft, setDraft] = useState<string | null>(null);

  function commit() {
    if (draft !== null) {
      const parsed = parseTimecode(draft);
      if (parsed !== null) onCommit(parsed);
    }
    setDraft(null);
  }

  return (
    <label className="flex items-center gap-1.5 text-xs text-ink-3">
      {label}
      <input
        id={id}
        value={draft ?? formatTimecode(value)}
        disabled={disabled}
        inputMode="numeric"
        aria-label={`${label} time`}
        onFocus={(e) => e.currentTarget.select()}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") {
            setDraft(null);
            e.currentTarget.blur();
          }
        }}
        className={cn(
          "h-8 w-16 rounded-full border border-line bg-surface-2 text-center font-mono text-xs text-ink transition-colors focus:border-accent focus:outline-none",
          disabled && "opacity-50",
        )}
      />
    </label>
  );
}
