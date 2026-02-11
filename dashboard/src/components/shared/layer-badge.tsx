"use client";

import { cn } from "@/lib/utils/format";

export function LayerBadge({ layer }: { layer: string }) {
  const isSml = layer === "sml";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide",
        isSml
          ? "bg-cyan-50 text-cyan-700 ring-1 ring-cyan-200"
          : "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
      )}
    >
      {layer}
    </span>
  );
}
