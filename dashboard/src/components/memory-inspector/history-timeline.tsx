"use client";

import { formatDateTime } from "@/lib/utils/format";
import type { MemoryHistoryEntry } from "@/lib/types/memory";

const EVENT_COLORS: Record<string, string> = {
  CREATE: "bg-green-400",
  DECAY: "bg-orange-400",
  PROMOTE: "bg-amber-400",
  DEMOTE: "bg-cyan-400",
  ACCESS: "bg-blue-400",
  UPDATE: "bg-purple-400",
  DELETE: "bg-red-400",
};

export function HistoryTimeline({ entries }: { entries: MemoryHistoryEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-sm text-gray-400">No history available.</p>;
  }

  return (
    <div className="relative">
      <div className="absolute left-2 top-0 bottom-0 w-px bg-gray-200" />
      <ul className="space-y-4">
        {entries.map((entry, i) => (
          <li key={i} className="relative pl-7">
            <div
              className={`absolute left-0.5 top-1 h-3 w-3 rounded-full ring-2 ring-white ${
                EVENT_COLORS[entry.event] || "bg-gray-400"
              }`}
            />
            <p className="text-xs font-medium text-gray-900">{entry.event}</p>
            <p className="text-[11px] text-gray-400">
              {formatDateTime(entry.timestamp)}
            </p>
            {entry.details && (
              <pre className="mt-1 text-[10px] text-gray-500 bg-gray-50 rounded p-1.5 overflow-x-auto">
                {JSON.stringify(entry.details, null, 2)}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
