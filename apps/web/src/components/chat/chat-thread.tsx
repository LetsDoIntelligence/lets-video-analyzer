"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "@/components/chat/message-bubble";
import { useChatStore } from "@/store/chat-store";

/** Scrolling message history that follows new content unless the user scrolled up. */
export function ChatThread() {
  const messages = useChatStore((s) => s.messages);
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTo({ top: el.scrollHeight });
  }, [messages]);

  return (
    <div
      ref={ref}
      role="log"
      aria-live="polite"
      aria-label="Conversation"
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }}
      className="flex flex-1 flex-col gap-6 overflow-y-auto px-4 py-5"
    >
      {messages.map((m) => (
        <div key={m.id} className="animate-rise">
          <MessageBubble message={m} />
        </div>
      ))}
    </div>
  );
}
