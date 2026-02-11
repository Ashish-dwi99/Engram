"use client";

import { useState } from "react";
import { useConflicts } from "@/lib/hooks/use-conflicts";
import { ConflictCard } from "@/components/conflicts/conflict-card";
import { EmptyState } from "@/components/shared/empty-state";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils/format";

export default function ConflictsPage() {
  const [tab, setTab] = useState<"UNRESOLVED" | "RESOLVED">("UNRESOLVED");
  const { data, mutate } = useConflicts(tab === "UNRESOLVED" ? "UNRESOLVED" : undefined);

  const conflicts = (data?.conflicts ?? []).filter((c) => {
    if (tab === "UNRESOLVED") return !c.resolution;
    return !!c.resolution;
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Conflicts</h1>
        <p className="text-sm text-gray-500">Resolve memory conflicts</p>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {(["UNRESOLVED", "RESOLVED"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors capitalize",
              tab === t
                ? "border-purple-600 text-purple-700"
                : "border-transparent text-gray-500 hover:text-gray-700"
            )}
          >
            {t.toLowerCase()}
          </button>
        ))}
      </div>

      {conflicts.length === 0 ? (
        <EmptyState
          title={tab === "UNRESOLVED" ? "No unresolved conflicts" : "No resolved conflicts"}
          description="Conflicts appear when new memories contradict existing ones."
          icon={AlertTriangle}
        />
      ) : (
        <div className="space-y-3">
          {conflicts.map((conflict) => (
            <ConflictCard
              key={conflict.id}
              conflict={conflict}
              onResolved={() => mutate()}
            />
          ))}
        </div>
      )}
    </div>
  );
}
