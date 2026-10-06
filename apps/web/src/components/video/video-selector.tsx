"use client";

import { Check, ChevronDown, Film, Trash2, Upload } from "lucide-react";
import * as Popover from "@radix-ui/react-popover";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/videos";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";

export function VideoSelector({ onUploadClick }: { onUploadClick: () => void }) {
  const [open, setOpen] = useState(false);
  const videos = useVideoStore((s) => s.videos);
  const selected = useVideoStore(selectSelectedVideo);
  const select = useVideoStore((s) => s.select);
  const remove = useVideoStore((s) => s.remove);

  const uploads = videos.filter((v) => v.source === "upload");
  const samples = videos.filter((v) => v.source === "sample");

  function pick(id: string) {
    select(id);
    setOpen(false);
  }

  function Row({ id }: { id: string }) {
    const v = videos.find((x) => x.id === id)!;
    const active = v.id === selected?.id;
    return (
      <li className="group relative">
        <button
          type="button"
          role="option"
          aria-selected={active}
          onClick={() => pick(v.id)}
          className={cn(
            "flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-accent-soft",
            active && "bg-accent-soft",
          )}
        >
          <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-3 text-ink-2">
            {v.thumbnailSrc ? (
              // eslint-disable-next-line @next/next/no-img-element -- small API-served thumbnail
              <img src={v.thumbnailSrc} alt="" className="size-full object-cover" />
            ) : (
              <Film className="size-4" />
            )}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-ink">{v.name}</span>
            <span className="block truncate text-xs text-ink-3">
              {v.durationSec ? formatDuration(v.durationSec) : "—"}
              {v.description ? ` · ${v.description}` : ""}
            </span>
          </span>
          {active && <Check className="size-4 shrink-0 text-accent" />}
        </button>
        {v.source === "upload" && (
          <button
            type="button"
            aria-label={`Remove ${v.name}`}
            onClick={() => void remove(v.id)}
            className="absolute top-1/2 right-10 -translate-y-1/2 cursor-pointer rounded-md p-1.5 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100 hover:text-danger focus-visible:opacity-100"
          >
            <Trash2 className="size-3.5" />
          </button>
        )}
      </li>
    );
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          id="video-select"
          type="button"
          aria-haspopup="listbox"
          className="flex h-9 w-full min-w-0 cursor-pointer items-center justify-between gap-3 rounded-full border border-line bg-surface-2 px-4 text-sm text-ink transition-colors hover:border-line-strong data-[state=open]:border-accent sm:w-64"
        >
          <span className={cn("truncate", !selected && "text-ink-2")}>
            {selected?.name ?? "Select video"}
          </span>
          <ChevronDown
            className={cn("size-4 shrink-0 text-ink-3 transition-transform", open && "rotate-180")}
          />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 w-[min(22rem,calc(100vw-2rem))] origin-top rounded-2xl border border-line-strong bg-surface p-2 shadow-lg data-[state=open]:animate-rise"
        >
          <ul role="listbox" aria-label="Videos" className="max-h-80 overflow-y-auto">
            {uploads.length > 0 && (
              <>
                <li className="px-3 pt-1 pb-1 text-[11px] font-medium tracking-wider text-ink-3 uppercase">
                  Your uploads
                </li>
                {uploads.map((v) => (
                  <Row key={v.id} id={v.id} />
                ))}
              </>
            )}
            <li className="px-3 pt-2 pb-1 text-[11px] font-medium tracking-wider text-ink-3 uppercase">
              Sample library
            </li>
            {samples.map((v) => (
              <Row key={v.id} id={v.id} />
            ))}
          </ul>
          <div className="mt-2 border-t border-line pt-2">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onUploadClick();
              }}
              className="flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-accent transition-colors hover:bg-accent-soft"
            >
              <Upload className="size-4" />
              Upload a video
            </button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
