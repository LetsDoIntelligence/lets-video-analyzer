import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-all duration-300 ease-premium disabled:pointer-events-none disabled:opacity-40 active:scale-[0.97] cursor-pointer",
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-accent-ink shadow-sm hover:bg-accent-hover hover:shadow-[0_8px_24px_-8px_var(--accent)]",
        secondary:
          "bg-surface-3 text-ink border border-line hover:border-line-strong hover:bg-surface-2",
        outline: "border border-line-strong text-ink hover:bg-accent-soft hover:border-accent",
        ghost: "text-ink-2 hover:text-ink hover:bg-accent-soft",
      },
      size: {
        sm: "h-8 px-3.5",
        md: "h-10 px-5",
        lg: "h-12 px-7 text-base",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = React.ComponentProps<"button"> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { buttonVariants };
