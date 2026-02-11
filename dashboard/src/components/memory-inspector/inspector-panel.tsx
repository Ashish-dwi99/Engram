"use client";

import { useEffect } from "react";
import { X } from "lucide-react";
import { useInspectorStore } from "@/lib/stores/inspector-store";
import { useMemory, useMemoryHistory } from "@/lib/hooks/use-memory";
import { FadeMemTab } from "./fadem-tab";
import { EchoTab } from "./echo-tab";
import { CategoryTab } from "./category-tab";
import { HistoryTimeline } from "./history-timeline";
import { InspectorActions } from "./inspector-actions";
import { cn } from "@/lib/utils/format";
import { useState } from "react";

const TABS = ["FadeMem", "EchoMem", "CategoryMem", "History"] as const;
type Tab = (typeof TABS)[number];

function InspectorContent() {
  const { selectedMemoryId, close } = useInspectorStore();
  const { data: memory, mutate } = useMemory(selectedMemoryId);
  const { data: history } = useMemoryHistory(selectedMemoryId);
  const [activeTab, setActiveTab] = useState<Tab>("FadeMem");

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [close]);

  if (!memory) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400 text-sm">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-gray-200 px-5 py-4">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-500 font-mono truncate">{memory.id}</p>
          <p className="mt-1 text-sm text-gray-900 line-clamp-3">{memory.content}</p>
        </div>
        <button onClick={close} className="ml-3 p-1 hover:bg-gray-100 rounded">
          <X className="h-4 w-4 text-gray-400" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 px-5">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              "px-3 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px",
              activeTab === tab
                ? "border-purple-600 text-purple-700"
                : "border-transparent text-gray-500 hover:text-gray-700"
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {activeTab === "FadeMem" && <FadeMemTab memory={memory} />}
        {activeTab === "EchoMem" && <EchoTab memory={memory} />}
        {activeTab === "CategoryMem" && <CategoryTab memory={memory} />}
        {activeTab === "History" && <HistoryTimeline entries={history || []} />}
      </div>

      {/* Actions */}
      <InspectorActions memory={memory} onMutate={mutate} />
    </div>
  );
}

export function InspectorWrapper() {
  const { isOpen } = useInspectorStore();

  return (
    <div
      className={cn(
        "h-screen border-l border-gray-200 bg-white transition-all duration-200 overflow-hidden",
        isOpen ? "w-[480px]" : "w-0"
      )}
    >
      {isOpen && <InspectorContent />}
    </div>
  );
}
