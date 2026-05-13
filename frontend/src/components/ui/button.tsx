import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "success";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-accent hover:bg-accent-subtle text-slate-950 font-semibold",
  secondary:
    "bg-bg-subtle hover:bg-bg-card border border-border text-slate-200",
  danger: "bg-loss hover:opacity-90 text-white font-semibold",
  success: "bg-profit hover:opacity-90 text-white font-semibold",
  ghost: "hover:bg-bg-subtle text-slate-200",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm transition-colors",
        "focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variantClasses[variant],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
