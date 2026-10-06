"use client";

import { UploadCloud, X } from "lucide-react";
import { useCallback, useState } from "react";
import { VideoPlayer } from "@/components/video/video-player";
import { cn } from "@/lib/utils";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";

/** Fills the video area: dropzone when empty, preview when a video is chosen. */
export function VideoStage({ onBrowse }: { onBrowse: () => void }) {
  const selected = useVideoStore(selectSelectedVideo);
  const upload = useVideoStore((s) => s.upload);
  const error = useVideoStore((s) => s.uploadError);
  const clearError = useVideoStore((s) => s.clearError);
  const progress = useVideoStore((s) => s.uploadProgress);
  const uploading = progress !== null;
  const [dragging, setDragging] = useState(false);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void upload(file);
    },
    [upload],
  );

  const frame =
    "relative flex h-[max(110px,calc(30vh_-_70px))] max-h-56 w-full max-w-lg items-center justify-center overflow-hidden rounded-xl border bg-canvas";

  return (
    <div
      className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 overflow-hidden p-3"
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      {selected ? (
        <VideoPlayer key={selected.id} video={selected} />
      ) : (
        <button
          type="button"
          onClick={onBrowse}
          disabled={uploading}
          aria-busy={uploading}
          className={cn(
            frame,
            "cursor-pointer border-dashed transition-all duration-300 hover:border-accent disabled:cursor-progress",
            dragging ? "border-accent bg-accent-soft" : "border-line-strong",
          )}
        >
          <div className="relative flex flex-col items-center gap-3 px-6 text-center">
            <span
              className={cn(
                "flex size-12 items-center justify-center rounded-full border border-line-strong bg-surface text-ink-2 transition-transform duration-300",
                dragging && "scale-110 text-accent",
              )}
            >
              <UploadCloud className="size-5" />
            </span>
            <span className="text-sm font-medium text-ink">
              {uploading
                ? `Uploading… ${Math.round(progress * 100)}%`
                : dragging
                  ? "Drop to upload"
                  : "Drop a video here, or browse"}
            </span>
            {uploading ? (
              <span className="h-1 w-40 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                <span
                  className="block h-full rounded-full bg-accent transition-[width] duration-200"
                  style={{ width: `${Math.round(progress * 100)}%` }}
                />
              </span>
            ) : (
              <span className="text-xs text-ink-3">MP4, MOV, WebM · up to 2 GB</span>
            )}
          </div>
        </button>
      )}


      {error && (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-full bg-danger/12 px-4 py-1.5 text-sm text-danger"
        >
          {error}
          <button type="button" aria-label="Dismiss" onClick={clearError} className="cursor-pointer">
            <X className="size-3.5" />
          </button>
        </p>
      )}
    </div>
  );
}
