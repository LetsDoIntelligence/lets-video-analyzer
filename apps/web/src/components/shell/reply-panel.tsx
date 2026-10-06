"use client";

import { Sparkles, Trash2 } from "lucide-react";
import { useEffect } from "react";
import { ChatInput } from "@/components/chat/chat-input";
import { ChatThread } from "@/components/chat/chat-thread";
import { Card } from "@/components/ui/card";
import { useChatStore } from "@/store/chat-store";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";

function EmptyState() {
  const video = useVideoStore(selectSelectedVideo);
  return (
    <div className="flex flex-1 flex-col items-center justify-center min-h-0 gap-2 overflow-hidden p-4 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-accent-soft text-accent [@media(max-height:720px)]:hidden">
        <Sparkles className="size-5" />
      </span>
      <p className="font-display text-2xl font-semibold tracking-tight">
        {video ? `Ask about ${video.name}` : "Pick a video to begin"}
      </p>
      <p className="max-w-md text-sm text-ink-2 [@media(max-height:620px)]:hidden">
        {video
          ? "Type a question below or click a sample prompt. Answers appear here as text, tables and charts."
          : "Choose a video from the dropdown or drop a file onto the player, then ask anything about it."}
      </p>
    </div>
  );
}

export function ReplyPanel() {
  const count = useChatStore((s) => s.messages.length);
  const clear = useChatStore((s) => s.clear);

  // Restore saved conversation on the client only (avoids SSR mismatch).
  useEffect(() => {
    void useChatStore.persist.rehydrate();
  }, []);

  return (
    <Card className="flex min-h-[320px] flex-1 lg:min-h-0 flex-col overflow-hidden" aria-labelledby="reply-heading">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 id="reply-heading" className="font-display text-base font-semibold">
          Analysis
        </h2>
        {count > 0 && (
          <button
            type="button"
            id="chat-clear"
            onClick={clear}
            className="flex cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-1 text-xs text-ink-3 transition-colors hover:bg-accent-soft hover:text-ink"
          >
            <Trash2 className="size-3.5" />
            Clear
          </button>
        )}
      </div>

      {count === 0 ? <EmptyState /> : <ChatThread />}
      <ChatInput />
    </Card>
  );
}
