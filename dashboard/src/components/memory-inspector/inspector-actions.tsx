"use client";

import { useState } from "react";
import { ArrowUp, ArrowDown, Trash2, Pencil } from "lucide-react";
import { promoteMemory, demoteMemory, deleteMemory, updateMemory } from "@/lib/api/memories";
import { useInspectorStore } from "@/lib/stores/inspector-store";
import type { Memory } from "@/lib/types/memory";
import type { KeyedMutator } from "swr";

export function InspectorActions({
  memory,
  onMutate,
}: {
  memory: Memory;
  onMutate: KeyedMutator<Memory>;
}) {
  const close = useInspectorStore((s) => s.close);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState(memory.content);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [loading, setLoading] = useState(false);

  const handlePromote = async () => {
    setLoading(true);
    await promoteMemory(memory.id);
    await onMutate();
    setLoading(false);
  };

  const handleDemote = async () => {
    setLoading(true);
    await demoteMemory(memory.id);
    await onMutate();
    setLoading(false);
  };

  const handleDelete = async () => {
    setLoading(true);
    await deleteMemory(memory.id);
    setLoading(false);
    close();
  };

  const handleSaveEdit = async () => {
    setLoading(true);
    await updateMemory(memory.id, { content: editContent });
    await onMutate();
    setEditing(false);
    setLoading(false);
  };

  if (editing) {
    return (
      <div className="border-t border-gray-200 p-4 space-y-3">
        <textarea
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
          className="w-full rounded-md border border-gray-200 p-2 text-sm focus:border-purple-300 focus:outline-none focus:ring-1 focus:ring-purple-300"
          rows={3}
        />
        <div className="flex gap-2">
          <button
            onClick={handleSaveEdit}
            disabled={loading}
            className="rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            Save
          </button>
          <button
            onClick={() => {
              setEditing(false);
              setEditContent(memory.content);
            }}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  if (confirmDelete) {
    return (
      <div className="border-t border-gray-200 p-4">
        <p className="text-sm text-gray-700 mb-3">
          Delete this memory? This action cannot be undone.
        </p>
        <div className="flex gap-2">
          <button
            onClick={handleDelete}
            disabled={loading}
            className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            Confirm Delete
          </button>
          <button
            onClick={() => setConfirmDelete(false)}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="border-t border-gray-200 px-4 py-3 flex items-center gap-2">
      <button
        onClick={() => setEditing(true)}
        className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
      >
        <Pencil className="h-3 w-3" /> Edit
      </button>
      {memory.layer === "sml" ? (
        <button
          onClick={handlePromote}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md bg-amber-50 border border-amber-200 px-2.5 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50"
        >
          <ArrowUp className="h-3 w-3" /> Promote to LML
        </button>
      ) : (
        <button
          onClick={handleDemote}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md bg-cyan-50 border border-cyan-200 px-2.5 py-1.5 text-xs font-medium text-cyan-700 hover:bg-cyan-100 disabled:opacity-50"
        >
          <ArrowDown className="h-3 w-3" /> Demote to SML
        </button>
      )}
      <button
        onClick={() => setConfirmDelete(true)}
        className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-red-200 px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
      >
        <Trash2 className="h-3 w-3" /> Delete
      </button>
    </div>
  );
}
