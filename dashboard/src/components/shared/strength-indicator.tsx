"use client";

import { layerColor } from "@/lib/utils/colors";

export function StrengthIndicator({
  strength,
  layer,
  size = "sm",
}: {
  strength: number;
  layer: string;
  size?: "sm" | "md";
}) {
  const pct = Math.round(strength * 100);
  const color = layerColor(layer);
  const h = size === "sm" ? "h-1.5" : "h-2.5";

  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 rounded-full bg-gray-100 ${h}`}>
        <div
          className={`${h} rounded-full transition-all`}
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs text-gray-500 tabular-nums w-8 text-right">
        {pct}%
      </span>
    </div>
  );
}
