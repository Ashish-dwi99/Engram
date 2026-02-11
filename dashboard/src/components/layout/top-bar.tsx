"use client";

import { Search } from "lucide-react";
import { useFilterStore } from "@/lib/stores/filter-store";
import { useCallback, useState } from "react";

export function TopBar() {
  const setSearchQuery = useFilterStore((s) => s.setSearchQuery);
  const [value, setValue] = useState("");

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setSearchQuery(value);
    },
    [value, setSearchQuery]
  );

  return (
    <header className="flex h-14 items-center gap-4 border-b border-gray-200 bg-white px-6">
      <form onSubmit={handleSubmit} className="relative flex-1 max-w-md">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search memories..."
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-full rounded-md border border-gray-200 bg-gray-50 py-1.5 pl-9 pr-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-purple-300 focus:bg-white focus:outline-none focus:ring-1 focus:ring-purple-300"
        />
      </form>
    </header>
  );
}
