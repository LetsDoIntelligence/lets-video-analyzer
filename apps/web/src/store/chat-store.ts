import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { ChatMessage, ScopeInfo } from "@/lib/chat";
import { ApiError, getAnalyzerClient } from "@/lib/api/client";
import { chatMessageSchema } from "@/lib/api/schemas";
import { describeRange } from "@/lib/range";
import { useAnalysisStore } from "@/store/analysis-store";
import { selectSelectedVideo, useVideoStore } from "@/store/video-store";

interface ChatState {
  messages: ChatMessage[];
  streaming: boolean;
  error: string | null;
  /** Text to place in the input box (used by sample prompts, T8). */
  draft: string;
  send: (text: string) => Promise<void>;
  regenerate: (assistantId: string) => Promise<void>;
  stop: () => void;
  clear: () => void;
  setDraft: (text: string) => void;
  clearError: () => void;
}

let controller: AbortController | null = null;

const uid = () => crypto.randomUUID();

function currentScope(): ScopeInfo | null {
  const video = selectSelectedVideo(useVideoStore.getState());
  if (!video) return null;
  const duration = video.durationSec ?? 0;
  const stored = useAnalysisStore.getState().ranges[video.id];
  const range = stored ?? { start: 0, end: duration };
  return {
    videoId: video.id,
    videoName: video.name,
    start: range.start,
    end: range.end,
    duration,
    label: duration > 0 ? describeRange(range, duration) : "Entire video",
  };
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => {
      async function run(question: string, scope: ScopeInfo, assistantId: string) {
        controller = new AbortController();
        const { signal } = controller;
        const patch = (fn: (m: ChatMessage) => ChatMessage) =>
          set((s) => ({ messages: s.messages.map((m) => (m.id === assistantId ? fn(m) : m)) }));

        set({ streaming: true, error: null });
        try {
          for await (const ev of getAnalyzerClient().analyze({ question, scope }, signal)) {
            if (ev.type === "error") throw new ApiError(ev.message);
            if (ev.type === "text") patch((m) => ({ ...m, text: m.text + ev.chunk }));
            else patch((m) => ({ ...m, blocks: ev.blocks }));
          }
          patch((m) => ({ ...m, status: "done" }));
        } catch (e) {
          const aborted = e instanceof DOMException && e.name === "AbortError";
          const reason = !aborted && e instanceof Error ? e.message : undefined;
          patch((m) => ({ ...m, status: aborted ? "stopped" : "error", error: reason }));
        } finally {
          controller = null;
          set({ streaming: false });
        }
      }

      return {
        messages: [],
        streaming: false,
        error: null,
        draft: "",

        send: async (text) => {
          const question = text.trim();
          if (!question || get().streaming) return;
          const scope = currentScope();
          if (!scope) {
            set({ error: "Select a video first." });
            return;
          }
          const assistantId = uid();
          set((s) => ({
            draft: "",
            messages: [
              ...s.messages,
              { id: uid(), role: "user", text: question, status: "done", scope, createdAt: Date.now() },
              {
                id: assistantId,
                role: "assistant",
                text: "",
                status: "streaming",
                scope,
                createdAt: Date.now(),
              },
            ],
          }));
          await run(question, scope, assistantId);
        },

        regenerate: async (assistantId) => {
          if (get().streaming) return;
          const { messages } = get();
          const idx = messages.findIndex((m) => m.id === assistantId);
          const user = idx > 0 ? messages[idx - 1] : undefined;
          if (!user || user.role !== "user" || !user.scope) return;
          set((s) => ({
            messages: s.messages.map((m) =>
              m.id === assistantId
                ? { ...m, text: "", blocks: undefined, error: undefined, status: "streaming" }
                : m,
            ),
          }));
          await run(user.text, user.scope, assistantId);
        },

        stop: () => controller?.abort(),
        clear: () => {
          controller?.abort();
          set({ messages: [], error: null });
        },
        setDraft: (draft) => set({ draft }),
        clearError: () => set({ error: null }),
      };
    },
    {
      name: "lets-chat",
      version: 1,
      // Older saved chats have the same shape; `merge` below validates each message.
      migrate: (persisted) => persisted as { messages: ChatMessage[] },
      storage: createJSONStorage(() => localStorage),
      skipHydration: true, // rehydrated on the client to avoid SSR mismatches
      merge: (persisted, current) => {
        const raw = (persisted as { messages?: unknown[] } | undefined)?.messages;
        if (!Array.isArray(raw)) return current;
        const messages = raw.flatMap((m) => {
          const r = chatMessageSchema.safeParse(m);
          return r.success ? [r.data] : [];
        });
        return { ...current, messages };
      },
      partialize: (s) => ({
        messages: s.messages.map((m) =>
          m.status === "streaming" ? { ...m, status: "stopped" as const } : m,
        ),
      }),
    },
  ),
);
