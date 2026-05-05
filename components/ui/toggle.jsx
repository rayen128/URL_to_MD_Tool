"use client"

import * as React from "react"
import { cva } from "class-variance-authority";
import { Toggle as TogglePrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

const toggleVariants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-2 focus-visible:ring-[var(--green)]/40 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-60 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "!bg-[var(--secondary)] !text-[var(--ink-2)] hover:!bg-[var(--secondary-hover)] data-[state=on]:!bg-[var(--green-soft)] data-[state=on]:!text-[var(--green-2)] data-[state=on]:!font-medium",
        outline:
          "!bg-[var(--secondary)] !text-[var(--ink-2)] hover:!bg-[var(--secondary-hover)] hover:!text-[var(--navy)] data-[state=on]:!bg-[var(--green-soft)] data-[state=on]:!text-[var(--green-2)] data-[state=on]:!font-medium data-[state=on]:!ring-1 data-[state=on]:!ring-[var(--green)]/40 data-[state=on]:!ring-inset",
      },
      size: {
        default: "h-9 min-w-9 px-2",
        sm: "h-8 min-w-8 px-1.5",
        lg: "h-10 min-w-10 px-2.5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Toggle({
  className,
  variant,
  size,
  ...props
}) {
  return (
    <TogglePrimitive.Root
      data-slot="toggle"
      className={cn(toggleVariants({ variant, size, className }))}
      {...props} />
  );
}

export { Toggle, toggleVariants }
