"use client";

import { useProfiles } from "@/lib/hooks/use-profiles";
import { ProfileCard } from "@/components/profiles/profile-card";
import { EmptyState } from "@/components/shared/empty-state";
import { Users } from "lucide-react";

export default function ProfilesPage() {
  const { data, isLoading } = useProfiles();
  const profiles = data?.profiles ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Profiles</h1>
        <p className="text-sm text-gray-500">Character profiles and entities</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-200 border-t-purple-600" />
        </div>
      ) : profiles.length === 0 ? (
        <EmptyState
          title="No profiles yet"
          description="Profiles are auto-detected from conversations."
          icon={Users}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {profiles.map((profile) => (
            <ProfileCard key={profile.id} profile={profile} />
          ))}
        </div>
      )}
    </div>
  );
}
