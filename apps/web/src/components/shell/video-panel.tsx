"use client";

import { ChevronUp, Trash2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { ScopeBadge } from "@/components/video/scope-badge";
import { VideoSelector } from "@/components/video/video-selector";
import { VideoStage } from "@/components/video/video-stage";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui-store";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";

export function VideoPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useVideoStore((s) => s.upload);
  const collapsed = useUiStore((s) => s.videoCollapsed);
  const toggle = useUiStore((s) => s.toggleVideo);
  const selected = useVideoStore(selectSelectedVideo);
  const select = useVideoStore((s) => s.select);
  const remove = useVideoStore((s) => s.remove);
  const load = useVideoStore((s) => s.load);

  // Fetch saved uploads from the API (no-op in mock mode).
  useEffect(() => {
    void load();
  }, [load]);

  // Uploads are discarded; built-in samples are just unloaded.
  const unload = () => {
    if (!selected) return;
    if (selected.source === "upload") void remove(selected.id);
    else select(null);
  };

  const browse = () => inputRef.current?.click();

  return (
    <Card className="flex shrink-0 flex-col overflow-hidden" aria-labelledby="video-heading">
      <div
        className={cn(
          "flex items-center justify-between gap-3 px-4 py-3 transition-colors",
          !collapsed && "border-b border-line",
        )}
      >
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            id="video-collapse"
            onClick={toggle}
            aria-expanded={!collapsed}
            aria-controls="video-body"
            aria-label={collapsed ? "Expand video" : "Collapse video"}
            className="flex size-7 cursor-pointer items-center justify-center rounded-full text-ink-3 transition-colors hover:bg-accent-soft hover:text-ink"
          >
            <ChevronUp
              className={cn("size-4 transition-transform duration-500", collapsed && "rotate-180")}
            />
          </button>
          <h2 id="video-heading" className="font-display text-base font-semibold">
            Video
          </h2>
          <ScopeBadge />
        </div>
        <div className="flex items-center gap-2">
          <VideoSelector onUploadClick={browse} />
          {selected && (
            <button
              type="button"
              id="video-unload"
              onClick={unload}
              aria-label="Remove video"
              title="Remove video"
              className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full border border-line text-ink-3 transition-colors hover:border-danger hover:bg-danger/10 hover:text-danger"
            >
              <Trash2 className="size-4" />
            </button>
          )}
        </div>
      </div>

      {/* Kept mounted while collapsed so playback and the playhead survive. */}
      <div
        id="video-body"
        inert={collapsed}
        className={cn(
          "grid transition-[grid-template-rows] duration-500 ease-premium",
          collapsed ? "grid-rows-[0fr]" : "grid-rows-[1fr]",
        )}
      >
        <div className="min-h-0 overflow-hidden">
          <VideoStage onBrowse={browse} />
        </div>
      </div>

      <input
        ref={inputRef}
        id="video-file-input"
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void upload(file);
          e.target.value = "";
        }}
      />
    </Card>
  );
}
