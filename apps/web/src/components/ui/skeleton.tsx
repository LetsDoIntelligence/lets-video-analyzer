import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "animate-[shimmer_1.8s_linear_infinite] rounded-lg bg-[linear-gradient(90deg,var(--surface-2),var(--surface-3),var(--surface-2))] bg-[length:200%_100%]",
        className,
      )}
      {...props}
    />
  );
}
