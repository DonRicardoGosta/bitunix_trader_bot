import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "w-full rounded-md bg-bg-subtle border border-border px-3 py-2 text-sm text-slate-100",
      "placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent",
      "disabled:opacity-50 disabled:cursor-not-allowed",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";

export const Label = ({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) => (
  <label
    className={cn("block text-xs uppercase tracking-wide text-muted mb-1", className)}
    {...props}
  />
);

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "w-full rounded-md bg-bg-subtle border border-border px-3 py-2 text-sm text-slate-100",
      "focus:outline-none focus:ring-2 focus:ring-accent",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";
