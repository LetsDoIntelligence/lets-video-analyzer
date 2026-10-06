"use client";

import { ArrowUp, Film, Square } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { describeRange } from "@/lib/range";
import { useAnalysisStore } from "@/store/analysis-store";
import { useChatStore } from "@/store/chat-store";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";

function ScopeLine() {
  const video = useVideoStore(selectSelectedVideo);
  const range = useAnalysisStore((s) => (video ? s.ranges[video.id] : undefined));
  const error = useChatStore((s) => s.error);
  const duration = video?.durationSec ?? 0;

  if (error) {
    return (
      <p role="alert" className="px-5 pb-2 text-xs text-danger">
        {error}
      </p>
    );
  }
  return (
    <p className="flex items-center gap-1.5 px-5 pb-2 text-xs text-ink-3">
      <Film className="size-3" />
      {video ? (
        <>
          Asking about <span className="text-ink-2">{video.name}</span> ·{" "}
          {duration > 0 ? describeRange(range ?? { start: 0, end: duration }, duration) : "Entire video"}
        </>
      ) : (
        "Select a video to start"
      )}
    </p>
  );
}

export function ChatInput() {
  const send = useChatStore((s) => s.send);
  const stop = useChatStore((s) => s.stop);
  const streaming = useChatStore((s) => s.streaming);
  const draft = useChatStore((s) => s.draft);
  const setDraft = useChatStore((s) => s.setDraft);
  const clearError = useChatStore((s) => s.clearError);
  const hasVideo = Boolean(useVideoStore(selectSelectedVideo));
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow up to ~5 lines.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [draft]);

  function submit() {
    if (streaming) return;
    void send(draft);
  }

  return (
    <div>
      <ScopeLine />
      <form
        className="px-3 pb-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="flex items-end gap-2 rounded-3xl border border-line bg-surface-2 py-1.5 pr-1.5 pl-5 transition-colors focus-within:border-accent">
          <textarea
            ref={ref}
            id="chat-input"
            rows={1}
            value={draft}
            disabled={!hasVideo}
            aria-label="Ask a question about the video"
            placeholder={hasVideo ? "How many cars passed between 3:00 and 6:00?" : "Select a video to start asking"}
            onChange={(e) => {
              setDraft(e.target.value);
              clearError();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            className="max-h-[120px] min-w-0 flex-1 resize-none self-center bg-transparent py-1.5 text-sm text-ink placeholder:text-ink-3 focus:outline-none disabled:cursor-not-allowed"
          />
          {streaming ? (
            <Button type="button" size="icon" variant="secondary" onClick={stop} aria-label="Stop generating" id="chat-stop">
              <Square className="size-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon"
              id="chat-send"
              aria-label="Send"
              disabled={!hasVideo || !draft.trim()}
            >
              <ArrowUp className="size-4" />
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}
