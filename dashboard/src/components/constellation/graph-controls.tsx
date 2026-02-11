"use client";

import { ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import { useGraphStore } from "@/lib/stores/graph-store";

export function GraphControls() {
  const { showSml, showLml, toggleSml, toggleLml, resetView } = useGraphStore();

  return (
    <div className="absolute top-4 right-4 flex flex-col gap-2">
      <div className="flex flex-col gap-1 rounded-lg border border-gray-200 bg-white p-1 shadow-sm">
        <button
          onClick={resetView}
          className="p-1.5 hover:bg-gray-100 rounded text-gray-500"
          title="Reset view"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-2 shadow-sm space-y-1.5">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showSml}
            onChange={toggleSml}
            className="h-3 w-3 rounded border-gray-300 text-cyan-500 focus:ring-cyan-400"
          />
          <span className="text-xs text-gray-600">SML</span>
          <span className="h-2 w-2 rounded-full bg-cyan-500" />
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showLml}
            onChange={toggleLml}
            className="h-3 w-3 rounded border-gray-300 text-amber-500 focus:ring-amber-400"
          />
          <span className="text-xs text-gray-600">LML</span>
          <span className="h-2 w-2 rounded-full bg-amber-500" />
        </label>
      </div>
    </div>
  );
}
