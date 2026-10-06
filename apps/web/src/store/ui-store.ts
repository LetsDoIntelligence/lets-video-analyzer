import { create } from "zustand";

interface UiState {
  /** Collapses the video panel to its header so rich answers get more room. */
  videoCollapsed: boolean;
  setVideoCollapsed: (collapsed: boolean) => void;
  toggleVideo: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  videoCollapsed: false,
  setVideoCollapsed: (videoCollapsed) => set({ videoCollapsed }),
  toggleVideo: () => set((s) => ({ videoCollapsed: !s.videoCollapsed })),
}));
