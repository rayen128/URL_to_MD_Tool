import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const sizes = { xs: "size-3", sm: "size-4", md: "size-5", lg: "size-6" };

export function Spinner({ size = "sm", className, ...props }) {
  return <Loader2 className={cn("animate-spin", sizes[size] || sizes.sm, className)} {...props} />;
}
