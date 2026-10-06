import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-11 w-full rounded-full border border-line bg-surface-2 px-5 text-sm text-ink placeholder:text-ink-3 transition-colors duration-300 focus:border-accent focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}
