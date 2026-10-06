import { ThemeToggle } from "@/components/theme-toggle";

function LogoMark() {
  return (
    <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
      <rect width="32" height="32" rx="10" className="fill-accent" />
      <path d="M13 10.5v11l9-5.5-9-5.5Z" className="fill-accent-ink" />
    </svg>
  );
}

export function AppHeader() {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-line px-5 lg:px-8">
      <div className="flex items-center gap-3">
        <LogoMark />
        <h1 className="font-display text-xl font-semibold tracking-tight">
          LETS <span className="text-ink-2 font-medium">Video Analyzer</span>
        </h1>
      </div>
      <ThemeToggle />
    </header>
  );
}
