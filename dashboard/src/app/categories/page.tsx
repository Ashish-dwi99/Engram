"use client";

import { useCategoryTree, useCategories } from "@/lib/hooks/use-categories";
import { CategoryTree } from "@/components/categories/category-tree";
import { EmptyState } from "@/components/shared/empty-state";
import { FolderTree } from "lucide-react";

export default function CategoriesPage() {
  const { data: treeData, isLoading: treeLoading } = useCategoryTree();
  const { data: flatData } = useCategories();

  // Use tree data if available, fall back to flat list
  const categories = treeData?.tree ?? flatData?.categories ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Categories</h1>
        <p className="text-sm text-gray-500">
          Hierarchical memory organization
        </p>
      </div>

      {treeLoading ? (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-200 border-t-purple-600" />
        </div>
      ) : categories.length === 0 ? (
        <EmptyState
          title="No categories yet"
          description="Categories are auto-discovered from your memories."
          icon={FolderTree}
        />
      ) : (
        <CategoryTree categories={categories} />
      )}
    </div>
  );
}
