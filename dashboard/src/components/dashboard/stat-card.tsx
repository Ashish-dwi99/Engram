"use client";

import type { LucideIcon } from "lucide-react";

export function StatCard({
  label,
  value,
  icon: Icon,
  color = "#7c3aed",
  badge,
}: {
  label: string;
  value: number | string;
  icon: LucideIcon;
  color?: string;
  badge?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 hover:shadow-sm transition-shadow">
      <div className="flex items-center justify-between">
        <div
          className="flex h-9 w-9 items-center justify-center rounded-lg"
          style={{ backgroundColor: color + "14" }}
        >
          <Icon className="h-4.5 w-4.5" style={{ color }} />
        </div>
        {badge && (
          <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-600 ring-1 ring-red-200">
            {badge}
          </span>
        )}
      </div>
      <p className="mt-3 text-2xl font-semibold text-gray-900 tabular-nums">{value}</p>
      <p className="mt-0.5 text-xs text-gray-500">{label}</p>
    </div>
  );
}
