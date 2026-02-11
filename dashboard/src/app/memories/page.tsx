"use client";

import { useMemories } from "@/lib/hooks/use-memories";
import { useFilterStore } from "@/lib/stores/filter-store";
import { MemoryTable } from "@/components/memories/memory-table";
import { MemoryFilters } from "@/components/memories/memory-filters";
import { EmptyState } from "@/components/shared/empty-state";
import { List } from "lucide-react";

export default function MemoriesPage() {
  const layer = useFilterStore((s) => s.layer);
  const { data, isLoading } = useMemories({
    layer: layer === "all" ? undefined : layer,
    limit: 200,
  });

  const memories = data?.memories ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Memories</h1>
          <p className="text-sm text-gray-500">
            {data ? `${data.count} memories` : "Loading..."}
          </p>
        </div>
        <MemoryFilters />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-200 border-t-purple-600" />
        </div>
      ) : memories.length === 0 ? (
        <EmptyState
          title="No memories found"
          description="Memories will appear here once added."
          icon={List}
        />
      ) : (
        <MemoryTable memories={memories} />
      )}
    </div>
  );
}
