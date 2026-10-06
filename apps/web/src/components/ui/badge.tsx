import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium tracking-wide",
  {
    variants: {
      tone: {
        neutral: "border-line text-ink-2 bg-surface-2",
        accent: "border-transparent bg-accent-soft text-accent",
        positive: "border-transparent bg-positive/12 text-positive",
        danger: "border-transparent bg-danger/12 text-danger",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
