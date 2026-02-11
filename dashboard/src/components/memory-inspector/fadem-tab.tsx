"use client";

import { LayerBadge } from "@/components/shared/layer-badge";
import { StrengthIndicator } from "@/components/shared/strength-indicator";
import {
  decayProjectionSeries,
  FORGET_THRESHOLD,
  PROMOTE_THRESHOLD,
  PROMOTE_ACCESS_THRESHOLD,
} from "@/lib/utils/decay-math";
import { timeAgo } from "@/lib/utils/format";
import { COLORS } from "@/lib/utils/colors";
import type { Memory } from "@/lib/types/memory";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

function StrengthRing({ strength, layer }: { strength: number; layer: string }) {
  const pct = strength * 100;
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (pct / 100) * circumference;
  const color = layer === "sml" ? COLORS.sml : COLORS.lml;

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="96" height="96" viewBox="0 0 96 96">
        <circle cx="48" cy="48" r="40" fill="none" stroke="#f3f4f6" strokeWidth="6" />
        <circle
          cx="48"
          cy="48"
          r="40"
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 48 48)"
          className="transition-all duration-500"
        />
      </svg>
      <span className="absolute text-lg font-semibold text-gray-900">
        {Math.round(pct)}%
      </span>
    </div>
  );
}

function ProgressBar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = Math.min((value / max) * 100, 100);
  const met = value >= max;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-500">{label}</span>
        <span className={met ? "text-green-600 font-medium" : "text-gray-500"}>
          {value} / {max}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-100">
        <div
          className="h-1.5 rounded-full transition-all"
          style={{
            width: `${pct}%`,
            backgroundColor: met ? "#22c55e" : "#d4d4d4",
          }}
        />
      </div>
    </div>
  );
}

export function FadeMemTab({ memory }: { memory: Memory }) {
  const series = decayProjectionSeries(
    memory.strength,
    memory.access_count,
    memory.layer
  );

  return (
    <div className="space-y-6">
      {/* Strength ring + metadata */}
      <div className="flex items-center gap-5">
        <StrengthRing strength={memory.strength} layer={memory.layer} />
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <LayerBadge layer={memory.layer} />
          </div>
          <p className="text-xs text-gray-500">
            Accessed {memory.access_count} time{memory.access_count !== 1 ? "s" : ""}
          </p>
          {memory.last_accessed && (
            <p className="text-xs text-gray-500">
              Last accessed {timeAgo(memory.last_accessed)}
            </p>
          )}
        </div>
      </div>

      {/* 30-day decay projection */}
      <div>
        <h4 className="text-xs font-medium text-gray-700 mb-2">
          30-Day Decay Projection
        </h4>
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="decayGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="5%"
                    stopColor={memory.layer === "sml" ? COLORS.sml : COLORS.lml}
                    stopOpacity={0.3}
                  />
                  <stop
                    offset="95%"
                    stopColor={memory.layer === "sml" ? COLORS.sml : COLORS.lml}
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <XAxis dataKey="day" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis
                domain={[0, 1]}
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={28}
              />
              <Tooltip
                contentStyle={{ fontSize: 11 }}
                formatter={(v) => [`${(Number(v) * 100).toFixed(1)}%`, "Strength"]}
                labelFormatter={(l) => `Day ${l}`}
              />
              <ReferenceLine y={FORGET_THRESHOLD} stroke="#ef4444" strokeDasharray="3 3" />
              <ReferenceLine y={PROMOTE_THRESHOLD} stroke="#22c55e" strokeDasharray="3 3" />
              <Area
                type="monotone"
                dataKey="strength"
                stroke={memory.layer === "sml" ? COLORS.sml : COLORS.lml}
                fill="url(#decayGrad)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="flex gap-4 mt-1 text-[10px] text-gray-400">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-px bg-red-400" /> Forget ({FORGET_THRESHOLD})
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-px bg-green-400" /> Promote ({PROMOTE_THRESHOLD})
          </span>
        </div>
      </div>

      {/* Promotion pathway */}
      {memory.layer === "sml" && (
        <div>
          <h4 className="text-xs font-medium text-gray-700 mb-3">
            Promotion Pathway (SML → LML)
          </h4>
          <div className="space-y-2.5">
            <ProgressBar
              value={memory.access_count}
              max={PROMOTE_ACCESS_THRESHOLD}
              label="Access count"
            />
            <ProgressBar
              value={memory.strength}
              max={PROMOTE_THRESHOLD}
              label="Strength"
            />
          </div>
        </div>
      )}

      {/* Current strength bar */}
      <div>
        <h4 className="text-xs font-medium text-gray-700 mb-2">Current Strength</h4>
        <StrengthIndicator strength={memory.strength} layer={memory.layer} size="md" />
      </div>
    </div>
  );
}
