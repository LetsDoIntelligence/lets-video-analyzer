"use client";

import {
  Film,
  Maximize,
  Pause,
  Play,
  RotateCcw,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { RangeTimeline } from "@/components/video/range-timeline";
import { TimeField } from "@/components/video/time-field";
import { Button } from "@/components/ui/button";
import { formatTimecode, isFullRange, withEnd, withStart } from "@/lib/range";
import { formatDuration, type VideoItem } from "@/lib/videos";
import { useAnalysisStore } from "@/store/analysis-store";

const RATES = [1, 1.5, 2, 0.5];

export function VideoPlayer({ video }: { video: VideoItem }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const lastSeekNonce = useRef<number | null>(null);

  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [elDuration, setElDuration] = useState<number>();

  const currentTime = useAnalysisStore((s) => s.currentTime);
  const setCurrentTime = useAnalysisStore((s) => s.setCurrentTime);
  const seekRequest = useAnalysisStore((s) => s.seekRequest);
  const storedRange = useAnalysisStore((s) => s.ranges[video.id]);
  const setStoredRange = useAnalysisStore((s) => s.setRange);

  const duration = video.durationSec ?? elDuration ?? 0;
  const range = storedRange ?? { start: 0, end: duration };
  const rangeActive = duration > 0 && !isFullRange(range, duration);
  const hasSrc = Boolean(video.src);
  const canRange = duration >= 2;

  const seek = useCallback(
    (t: number) => {
      const clamped = Math.min(Math.max(t, 0), duration || 0);
      if (videoRef.current) videoRef.current.currentTime = clamped;
      setCurrentTime(clamped);
    },
    [duration, setCurrentTime],
  );

  // Reset playhead when a video is loaded.
  useEffect(() => {
    setCurrentTime(0);
  }, [setCurrentTime]);

  // Handle seek requests from elsewhere (e.g. reply timestamp chips).
  useEffect(() => {
    if (seekRequest && seekRequest.nonce !== lastSeekNonce.current) {
      lastSeekNonce.current = seekRequest.nonce;
      seek(seekRequest.time);
    }
  }, [seekRequest, seek]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = rate;
  }, [rate]);

  // Smooth playhead + stop at the end of the selected window.
  useEffect(() => {
    if (!playing) return;
    let id = 0;
    const tick = () => {
      const v = videoRef.current;
      if (v) {
        setCurrentTime(v.currentTime);
        if (rangeActive && v.currentTime >= range.end) {
          v.pause();
          v.currentTime = range.end;
          setCurrentTime(range.end);
          return;
        }
      }
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [playing, rangeActive, range.end, setCurrentTime]);

  const setRange = (next: { start: number; end: number }) => setStoredRange(video.id, next);
  const setStart = (t: number) => canRange && setRange(withStart(range, t));
  const setEnd = (t: number) => canRange && setRange(withEnd(range, t, duration));

  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      if (rangeActive && (v.currentTime < range.start || v.currentTime >= range.end - 0.05)) {
        seek(range.start);
      }
      void v.play();
    } else {
      v.pause();
    }
  }

  function playRange() {
    seek(range.start);
    void videoRef.current?.play();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if ((e.target as HTMLElement).closest("input")) return;
    switch (e.key) {
      case " ":
      case "k":
        e.preventDefault();
        togglePlay();
        break;
      case "ArrowLeft":
        seek(currentTime - 5);
        break;
      case "ArrowRight":
        seek(currentTime + 5);
        break;
      case "m":
        setMuted((m) => !m);
        break;
      case "f":
        void shellRef.current?.requestFullscreen?.();
        break;
      case "[":
        setStart(currentTime);
        break;
      case "]":
        setEnd(currentTime);
        break;
    }
  }

  return (
    <div className="flex w-full max-w-3xl flex-col gap-1">
      <div
        ref={shellRef}
        tabIndex={0}
        onKeyDown={onKeyDown}
        className="group relative mx-auto aspect-video w-full max-w-[min(100%,calc(min(max(96px,calc(30vh_-_80px)),320px)*1.7778))] overflow-hidden rounded-xl border border-line bg-canvas outline-none focus-visible:border-accent"
      >
        {hasSrc ? (
          <video
            key={video.src}
            ref={videoRef}
            src={video.src}
            muted={muted}
            playsInline
            preload="metadata"
            onClick={togglePlay}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
            onTimeUpdate={(e) => !playing && setCurrentTime(e.currentTarget.currentTime)}
            onLoadedMetadata={(e) => setElDuration(e.currentTarget.duration)}
            className="size-full cursor-pointer object-contain"
          />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,var(--accent-soft),transparent_60%)]" />
            <span className="relative flex size-12 items-center justify-center rounded-full border border-line-strong bg-surface text-ink-2">
              <Film className="size-5" />
            </span>
            <p className="font-display relative text-lg font-semibold">{video.name}</p>
            <p className="relative text-xs text-ink-3">
              {duration ? formatDuration(duration) : ""} · Sample footage coming soon
            </p>
          </div>
        )}

        {hasSrc && !playing && (
          <button
            type="button"
            aria-label="Play"
            onClick={togglePlay}
            className="absolute inset-0 flex cursor-pointer items-center justify-center"
          >
            <span className="flex size-14 items-center justify-center rounded-full bg-canvas/70 text-ink backdrop-blur transition-transform duration-300 group-hover:scale-110">
              <Play className="ml-0.5 size-6 fill-current" />
            </span>
          </button>
        )}
      </div>

      <RangeTimeline
        duration={duration}
        currentTime={currentTime}
        range={range}
        rangeActive={rangeActive}
        onSeek={seek}
        onStartChange={setStart}
        onEndChange={setEnd}
      />

      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            id="player-play"
            disabled={!hasSrc}
            onClick={togglePlay}
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
          </Button>
          <span className="font-mono text-xs text-ink-2 tabular-nums">
            {formatTimecode(currentTime)} / {duration ? formatTimecode(duration) : "—"}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <TimeField
            id="range-start"
            label="From"
            value={range.start}
            disabled={!canRange}
            onCommit={setStart}
          />
          <TimeField
            id="range-end"
            label="To"
            value={range.end}
            disabled={!canRange}
            onCommit={setEnd}
          />
          {hasSrc && (
            <Button
              size="sm"
              variant="outline"
              onClick={playRange}
              id="range-play"
              aria-label="Play range"
              disabled={!canRange}
            >
              <Play className="size-3 fill-current" />
              <span className="hidden xl:inline">Play range</span>
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            id="range-reset"
            aria-label="Use entire video"
            title="Use entire video"
            disabled={!rangeActive}
            onClick={() => setStoredRange(video.id, null)}
          >
            <RotateCcw className="size-4" />
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={!hasSrc}
            onClick={() => setRate((r) => RATES[(RATES.indexOf(r) + 1) % RATES.length])}
            aria-label="Playback speed"
            className="font-mono text-xs tabular-nums"
          >
            {rate}×
          </Button>
          <Button
            variant="ghost"
            size="icon"
            disabled={!hasSrc}
            onClick={() => setMuted((m) => !m)}
            aria-label={muted ? "Unmute" : "Mute"}
          >
            {muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            disabled={!hasSrc}
            onClick={() => void shellRef.current?.requestFullscreen?.()}
            aria-label="Fullscreen"
          >
            <Maximize className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
