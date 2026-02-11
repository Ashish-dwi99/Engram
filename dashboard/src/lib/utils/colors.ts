export const COLORS = {
  sml: "#06b6d4",
  lml: "#f59e0b",
  brand: "#7c3aed",
  destructive: "#ef4444",
  success: "#22c55e",
  scene: "#6b7280",
  category: "#7c3aed",
  entity: "#7c3aed",
} as const;

export function layerColor(layer: string): string {
  return layer === "lml" ? COLORS.lml : COLORS.sml;
}

export function profileTypeColor(type: string): string {
  switch (type) {
    case "self":
      return COLORS.lml;
    case "contact":
      return COLORS.sml;
    case "entity":
      return COLORS.brand;
    default:
      return COLORS.scene;
  }
}
