"use client";

import { MemoryGraph } from "@/components/constellation/memory-graph";
import { GraphControls } from "@/components/constellation/graph-controls";
import { GraphLegend } from "@/components/constellation/graph-legend";

export default function ConstellationPage() {
  return (
    <div className="relative -m-6 h-[calc(100vh-3.5rem)]">
      <MemoryGraph />
      <GraphControls />
      <GraphLegend />
    </div>
  );
}
