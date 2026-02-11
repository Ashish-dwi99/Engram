"use client";

import { useScenes } from "@/lib/hooks/use-scenes";
import { SceneCard } from "@/components/scenes/scene-card";
import { EmptyState } from "@/components/shared/empty-state";
import { Film } from "lucide-react";

export default function ScenesPage() {
  const { data, isLoading } = useScenes();
  const scenes = data?.scenes ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Scenes</h1>
        <p className="text-sm text-gray-500">Episodic memory timeline</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-200 border-t-purple-600" />
        </div>
      ) : scenes.length === 0 ? (
        <EmptyState
          title="No scenes yet"
          description="Scenes group related memories into episodes."
          icon={Film}
        />
      ) : (
        <div className="space-y-3">
          {scenes.map((scene) => (
            <SceneCard key={scene.id} scene={scene} />
          ))}
        </div>
      )}
    </div>
  );
}
