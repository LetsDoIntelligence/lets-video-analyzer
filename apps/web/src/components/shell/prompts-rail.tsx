"use client";

import { ArrowUpRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { PROMPT_GROUPS } from "@/lib/sample-prompts";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat-store";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";

/** Click a prompt to ask it straight away against the current video + range. */
export function PromptsRail() {
  const send = useChatStore((s) => s.send);
  const streaming = useChatStore((s) => s.streaming);
  const hasVideo = Boolean(useVideoStore(selectSelectedVideo));

  function ask(text: string) {
    void send(text); // sets "Select a video first." when nothing is loaded
    // Desktop layout is fixed; only the stacked mobile layout needs to scroll.
    if (!window.matchMedia("(min-width: 1024px)").matches) {
      document
        .getElementById("reply-heading")
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  return (
    <Card className="flex min-h-0 flex-col overflow-hidden" aria-labelledby="prompts-heading">
      <div className="border-b border-line px-4 py-3">
        <h2 id="prompts-heading" className="font-display text-base font-semibold">
          Sample prompts
        </h2>
        <p className="mt-0.5 hidden text-xs text-ink-3 lg:block">
          {hasVideo ? "Click one to ask it now." : "Select a video, then click a prompt."}
        </p>
      </div>

      <ul className="flex gap-2 overflow-x-auto p-3 lg:flex-col lg:gap-1.5 lg:overflow-x-hidden lg:overflow-y-auto">
        {PROMPT_GROUPS.map((group) => (
          <li key={group.title} className="contents">
            <p className="hidden px-1 pt-2 pb-0.5 text-[11px] font-medium tracking-wider text-ink-3 uppercase first:pt-0 lg:block">
              {group.title}
            </p>
            <ul className="contents lg:flex lg:flex-col lg:gap-1.5">
              {group.prompts.map((p) => (
                <li key={p.id} className="shrink-0">
                  <button
                    type="button"
                    id={`prompt-${p.id}`}
                    disabled={streaming}
                    onClick={() => ask(p.text)}
                    className={cn(
                      "group flex w-full cursor-pointer items-center justify-between gap-3 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-left text-sm whitespace-nowrap text-ink-2 transition-all duration-300 hover:border-accent hover:bg-accent-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-50 lg:whitespace-normal",
                      !hasVideo && "opacity-80",
                    )}
                  >
                    {p.text}
                    <ArrowUpRight className="hidden size-4 shrink-0 text-ink-3 opacity-0 transition-all duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-accent group-hover:opacity-100 lg:block" />
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Card>
  );
}
