"use client";

import { useStats } from "@/lib/hooks/use-stats";
import { useConflicts } from "@/lib/hooks/use-conflicts";
import { useStaging } from "@/lib/hooks/use-staging";
import { useDecayLog } from "@/lib/hooks/use-decay-log";
import { StatCardsRow } from "@/components/dashboard/stat-cards-row";
import { LayerDonut } from "@/components/dashboard/layer-donut";
import { CategoriesBar } from "@/components/dashboard/categories-bar";
import { DecaySparkline } from "@/components/dashboard/decay-sparkline";

export default function DashboardPage() {
  const { data: stats } = useStats();
  const { data: conflicts } = useConflicts("UNRESOLVED");
  const { data: staging } = useStaging("PENDING");
  const { data: decayLog } = useDecayLog();

  const totalMemories = stats?.total_memories ?? 0;
  const smlCount = stats?.sml_count ?? 0;
  const lmlCount = stats?.lml_count ?? 0;
  const categoryCount = stats ? Object.keys(stats.categories).length : 0;
  const conflictCount = conflicts?.conflicts?.length ?? 0;
  const pendingCount = staging?.commits?.length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500">Memory kernel overview</p>
      </div>

      <StatCardsRow
        totalMemories={totalMemories}
        smlCount={smlCount}
        lmlCount={lmlCount}
        categoryCount={categoryCount}
        conflictCount={conflictCount}
        pendingCount={pendingCount}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <LayerDonut smlCount={smlCount} lmlCount={lmlCount} />
        <CategoriesBar categories={stats?.categories ?? {}} />
        <DecaySparkline entries={decayLog?.entries ?? []} />
      </div>
    </div>
  );
}
