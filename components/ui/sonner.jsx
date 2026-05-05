"use client"

import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { useTheme } from "next-themes"
import { Toaster as Sonner } from "sonner";

const Toaster = ({
  ...props
}) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      toastOptions={{
        classNames: {
          toast: "group !bg-[var(--paper)] !text-[var(--ink-2)] !border !border-[var(--line)] !shadow-none !rounded-lg !px-3 !py-2 !text-sm !font-normal !min-h-9",
          title: "!text-[var(--ink)] !font-medium !text-sm",
          description: "!text-[var(--muted)] !text-xs",
          icon: "!size-4",
          closeButton: "!bg-transparent !border-0 !text-[var(--muted)] hover:!text-[var(--navy)]",
          success: "!text-[var(--green-2)]",
          error: "!text-[var(--danger)]",
          warning: "!text-[var(--warning)]",
          info: "!text-[var(--ink-2)]",
        },
      }}
      style={
        {
          "--normal-bg": "var(--paper)",
          "--normal-text": "var(--ink-2)",
          "--normal-border": "var(--line)",
          "--border-radius": "var(--radius)"
        }
      }
      {...props} />
  );
}

export { Toaster }
