"use client";

import { Check, Copy, Film, RefreshCw } from "lucide-react";
import { useState } from "react";
import { BlockRenderer } from "@/components/chat/blocks/block-renderer";
import { RichText } from "@/components/chat/rich-text";
import type { ChatMessage } from "@/lib/chat";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat-store";

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-2" aria-label="Analyzing">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="size-1.5 animate-bounce rounded-full bg-ink-3"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </span>
  );
}

function Avatar() {
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-ink">
      <svg viewBox="0 0 32 32" className="size-4" aria-hidden>
        <path d="M13 10.5v11l9-5.5-9-5.5Z" fill="currentColor" />
      </svg>
    </span>
  );
}

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex flex-col items-end gap-1.5">
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-surface-3 px-4 py-2.5 text-sm text-ink">
        {message.text}
      </p>
      {message.scope && (
        <span className="flex items-center gap-1.5 pr-1 text-[11px] text-ink-3">
          <Film className="size-3" />
          {message.scope.videoName} · {message.scope.label}
        </span>
      )}
    </div>
  );
}

function AssistantBubble({ message }: { message: ChatMessage }) {
  const regenerate = useChatStore((s) => s.regenerate);
  const busy = useChatStore((s) => s.streaming);
  const [copied, setCopied] = useState(false);

  const streaming = message.status === "streaming";
  const waiting = streaming && message.text === "";

  async function copy() {
    await navigator.clipboard.writeText(message.text.replace(/\*\*/g, ""));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="group flex gap-3">
      <Avatar />
      <div className="min-w-0 flex-1 pt-0.5 text-sm leading-relaxed text-ink">
        {waiting ? (
          <TypingDots />
        ) : (
          <div className={cn(streaming && "after:ml-0.5 after:inline-block after:h-4 after:w-px after:translate-y-0.5 after:animate-pulse after:bg-accent")}>
            <RichText text={message.text} />
          </div>
        )}

        {message.blocks && message.blocks.length > 0 && (
          <BlockRenderer blocks={message.blocks} videoId={message.scope?.videoId} />
        )}

        {message.status === "stopped" && (
          <p className="mt-2 text-xs text-ink-3">Stopped.</p>
        )}
        {message.status === "error" && (
          <p role="alert" className="mt-2 text-xs text-danger">
            {message.error ?? "Something went wrong generating this answer."}
          </p>
        )}

        {!streaming && (
          <div className="mt-2 flex gap-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
            {message.text && (
              <button
                type="button"
                onClick={copy}
                className="flex cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-1 text-xs text-ink-3 transition-colors hover:bg-accent-soft hover:text-ink"
              >
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => void regenerate(message.id)}
              className="flex cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-1 text-xs text-ink-3 transition-colors hover:bg-accent-soft hover:text-ink disabled:opacity-40"
            >
              <RefreshCw className="size-3.5" />
              Regenerate
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  return message.role === "user" ? <UserBubble message={message} /> : <AssistantBubble message={message} />;
}
