import { create } from "zustand";
import { env } from "@/lib/env";
import { videosClient } from "@/lib/api/videos-client";
import {
  SAMPLE_VIDEOS,
  readVideoDuration,
  validateVideoFile,
  type VideoItem,
} from "@/lib/videos";

interface VideoState {
  videos: VideoItem[];
  selectedId: string | null;
  /** True while the saved-uploads list is being fetched from the API. */
  loading: boolean;
  /** 0..1 while a file is uploading to the API, otherwise null. */
  uploadProgress: number | null;
  uploadError: string | null;
  load: () => Promise<void>;
  select: (id: string | null) => void;
  upload: (file: File) => Promise<void>;
  remove: (id: string) => Promise<void>;
  clearError: () => void;
}

const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

/**
 * With `NEXT_PUBLIC_USE_MOCKS=true` uploads live only in this browser tab (blob URLs), so the
 * UI works with no backend. Otherwise they're stored by the API and survive reloads.
 */
export const useVideoStore = create<VideoState>((set, get) => ({
  videos: SAMPLE_VIDEOS,
  selectedId: null,
  loading: false,
  uploadProgress: null,
  uploadError: null,

  load: async () => {
    if (env.useMocks) return;
    set({ loading: true });
    try {
      const uploads = await videosClient.list();
      set((s) => ({
        videos: [...uploads, ...SAMPLE_VIDEOS],
        selectedId:
          s.selectedId && [...uploads, ...SAMPLE_VIDEOS].some((v) => v.id === s.selectedId)
            ? s.selectedId
            : null,
        uploadError: null,
      }));
    } catch (e) {
      set({ uploadError: message(e, "Couldn't load your videos.") });
    } finally {
      set({ loading: false });
    }
  },

  select: (id) => set({ selectedId: id }),

  upload: async (file) => {
    const error = validateVideoFile(file);
    if (error) {
      set({ uploadError: error });
      return;
    }

    if (env.useMocks) {
      const src = URL.createObjectURL(file);
      const durationSec = await readVideoDuration(src);
      const item: VideoItem = {
        id: `upload-${crypto.randomUUID()}`,
        name: file.name.replace(/\.[^.]+$/, ""),
        source: "upload",
        src,
        durationSec,
        sizeBytes: file.size,
      };
      set((s) => ({ videos: [item, ...s.videos], selectedId: item.id, uploadError: null }));
      return;
    }

    if (get().uploadProgress !== null) return; // one upload at a time
    set({ uploadProgress: 0, uploadError: null });
    try {
      const item = await videosClient.upload(file, (uploadProgress) => set({ uploadProgress }));
      set((s) => ({ videos: [item, ...s.videos], selectedId: item.id }));
    } catch (e) {
      set({ uploadError: message(e, "The upload failed.") });
    } finally {
      set({ uploadProgress: null });
    }
  },

  remove: async (id) => {
    const target = get().videos.find((v) => v.id === id);
    if (!target || target.source !== "upload") return;

    if (env.useMocks) {
      if (target.src) URL.revokeObjectURL(target.src);
    } else {
      try {
        await videosClient.remove(id);
      } catch (e) {
        set({ uploadError: message(e, "Couldn't remove the video.") });
        return;
      }
    }
    set((s) => ({
      videos: s.videos.filter((v) => v.id !== id),
      selectedId: s.selectedId === id ? null : s.selectedId,
    }));
  },

  clearError: () => set({ uploadError: null }),
}));

export const selectSelectedVideo = (s: VideoState) =>
  s.videos.find((v) => v.id === s.selectedId) ?? null;
