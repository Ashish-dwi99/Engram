"use client";

import { useState } from "react";
import { useStaging } from "@/lib/hooks/use-staging";
import { CommitCard } from "@/components/staging/commit-card";
import { EmptyState } from "@/components/shared/empty-state";
import { GitBranch } from "lucide-react";
import { cn } from "@/lib/utils/format";

const TABS = ["PENDING", "APPROVED", "REJECTED"] as const;

export default function StagingPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("PENDING");
  const { data, mutate } = useStaging(tab);

  const commits = data?.commits ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Staging</h1>
        <p className="text-sm text-gray-500">Review memory proposals</p>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
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

      {commits.length === 0 ? (
        <EmptyState
          title={`No ${tab.toLowerCase()} proposals`}
          description="Memory proposals from agents will appear here."
          icon={GitBranch}
        />
      ) : (
        <div className="space-y-3">
          {commits.map((commit) => (
            <CommitCard
              key={commit.id}
              commit={commit}
              onAction={() => mutate()}
            />
          ))}
        </div>
      )}
    </div>
  );
}
