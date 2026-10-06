import { AppHeader } from "@/components/shell/app-header";
import { PromptsRail } from "@/components/shell/prompts-rail";
import { ReplyPanel } from "@/components/shell/reply-panel";
import { VideoPanel } from "@/components/shell/video-panel";

export default function Home() {
  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh lg:overflow-hidden">
      <AppHeader />
      <main className="grid flex-1 grid-cols-[minmax(0,1fr)] gap-4 p-4 lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_320px] lg:grid-rows-[minmax(0,1fr)] lg:gap-5 lg:p-6">
        <div className="animate-rise flex min-h-0 flex-col gap-4 lg:gap-5 lg:overflow-hidden">
          <VideoPanel />
          <ReplyPanel />
        </div>
        <aside className="animate-rise order-first flex min-h-0 flex-col [animation-delay:120ms] lg:order-none">
          <PromptsRail />
        </aside>
      </main>
    </div>
  );
}
