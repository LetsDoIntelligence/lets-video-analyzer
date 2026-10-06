import { ThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata = { title: "Design system · LETS Video Analyzer" };

const swatches = [
  ["canvas", "bg-canvas"],
  ["surface", "bg-surface"],
  ["surface-2", "bg-surface-2"],
  ["surface-3", "bg-surface-3"],
  ["accent", "bg-accent"],
  ["positive", "bg-positive"],
  ["danger", "bg-danger"],
  ["ink", "bg-ink"],
];

export default function DesignPage() {
  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-14">
      <header className="animate-rise mb-14 flex items-start justify-between">
        <div>
          <p className="font-mono text-xs tracking-[0.2em] text-ink-3 uppercase">Design system</p>
          <h1 className="font-display mt-3 text-5xl font-semibold tracking-tight">
            LETS <span className="text-accent">Video</span> Analyzer
          </h1>
          <p className="mt-4 max-w-xl text-ink-2">
            Clear, calm and confident. Deep teal-blue with a soft green accent.
          </p>
        </div>
        <ThemeToggle />
      </header>

      <section className="mb-12">
        <h2 className="font-display mb-4 text-2xl">Colour</h2>
        <div className="grid grid-cols-4 gap-3 sm:grid-cols-8">
          {swatches.map(([name, cls]) => (
            <div key={name} className="space-y-2">
              <div className={`h-16 rounded-xl border border-line ${cls}`} />
              <p className="font-mono text-[11px] text-ink-3">{name}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-12">
        <h2 className="font-display mb-4 text-2xl">Type</h2>
        <Card>
          <CardContent className="space-y-3 pt-5">
            <p className="font-display text-4xl font-semibold tracking-tight">There were 42 cars.</p>
            <p className="text-ink-2">DM Sans for interface and body copy, set at comfortable weights.</p>
            <p className="font-mono text-sm text-ink-3">00:03:21.480 — DM Mono for data</p>
          </CardContent>
        </Card>
      </section>

      <section className="mb-12">
        <h2 className="font-display mb-4 text-2xl">Controls</h2>
        <div className="flex flex-wrap items-center gap-3">
          <Button>Analyze</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button size="sm">Small</Button>
          <Button disabled>Disabled</Button>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <Badge>Neutral</Badge>
          <Badge tone="accent">Accent</Badge>
          <Badge tone="positive">Indexed</Badge>
          <Badge tone="danger">Failed</Badge>
        </div>
        <div className="mt-5 max-w-md">
          <Input placeholder="Ask anything about this video…" />
        </div>
      </section>

      <section>
        <h2 className="font-display mb-4 text-2xl">Surfaces</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Vehicles detected</CardTitle>
              <p className="text-sm text-ink-3">Between 03:00 and 06:00</p>
            </CardHeader>
            <CardContent>
              <p className="font-display text-6xl font-semibold text-accent">128</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Loading</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-20 w-full" />
            </CardContent>
          </Card>
        </div>
      </section>
    </main>
  );
}
