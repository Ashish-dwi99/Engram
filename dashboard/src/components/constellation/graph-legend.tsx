"use client";

import { COLORS } from "@/lib/utils/colors";

const LEGEND_ITEMS = [
  { label: "SML Memory", color: COLORS.sml, shape: "circle" },
  { label: "LML Memory", color: COLORS.lml, shape: "circle" },
  { label: "Scene Link", color: COLORS.scene, shape: "line" },
  { label: "Category Link", color: COLORS.category, shape: "line" },
];

export function GraphLegend() {
  return (
    <div className="absolute bottom-4 left-4 rounded-lg border border-gray-200 bg-white/90 backdrop-blur-sm px-3 py-2 shadow-sm">
      <div className="flex gap-4">
        {LEGEND_ITEMS.map(({ label, color, shape }) => (
          <div key={label} className="flex items-center gap-1.5">
            {shape === "circle" ? (
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: color }}
              />
            ) : (
              <span
                className="h-px w-4"
                style={{ backgroundColor: color }}
              />
            )}
            <span className="text-[10px] text-gray-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
