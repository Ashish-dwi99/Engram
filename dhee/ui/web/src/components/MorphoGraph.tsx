import { useEffect, useRef, useState } from "react";

/* ── Types ── */
interface GraphNode {
  id: string;
  label: string;
  type: "memory" | "entity" | "category" | "fact" | "scene" | "episode" | "profile";
  subtype: string;
  strength: number;
  importance: number;
  // simulation
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
}
interface GraphEdge {
  source: number;
  target: number;
  type: string;
}
interface GraphStats {
  node_count: number;
  edge_count: number;
  memories: number;
  entities: number;
  categories: number;
  facts: number;
  scenes: number;
  episodes: number;
  profiles: number;
}

/* ── Color palette by node type ── */
const TYPE_COLORS: Record<string, string> = {
  memory: "#ff6b35",
  entity: "#00d4aa",
  category: "#a78bfa",
  fact: "#38bdf8",
  scene: "#facc15",
  episode: "#ef4444",
  profile: "#ec4899",
};
const TYPE_GLOW: Record<string, string> = {
  memory: "rgba(255,107,53,0.3)",
  entity: "rgba(0,212,170,0.25)",
  category: "rgba(167,139,250,0.3)",
  fact: "rgba(56,189,248,0.25)",
  scene: "rgba(250,204,21,0.2)",
  episode: "rgba(239,68,68,0.3)",
  profile: "rgba(236,72,153,0.3)",
};
const EDGE_COLORS: Record<string, string> = {
  belongs_to: "rgba(167,139,250,0.25)",
  extracted_from: "rgba(0,212,170,0.15)",
  fact_of: "rgba(56,189,248,0.15)",
  elaborates: "rgba(255,107,53,0.15)",
  causal: "rgba(255,200,50,0.2)",
  co_occurring: "rgba(200,200,200,0.1)",
  related: "rgba(200,200,200,0.12)",
  part_of: "rgba(239,68,68,0.2)",
  context_of: "rgba(250,204,21,0.15)",
};

export const MorphoGraph: React.FC<{ memoryId: string }> = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const edgesRef = useRef<GraphEdge[]>([]);
  const mouseRef = useRef({ x: 0, y: 0 });
  const panRef = useRef({ x: 0, y: 0, dragging: false, startX: 0, startY: 0, panStartX: 0, panStartY: 0 });
  const zoomRef = useRef(1);
  const frameRef = useRef(0);

  /* ── Fetch graph data ── */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/morpho/graph");
        const data = await res.json();
        if (cancelled) return;

        const rawNodes = data.nodes || [];
        const rawEdges = data.edges || [];

        // Initialize simulation positions in a circle
        const cx = 0, cy = 0, radius = Math.max(200, rawNodes.length * 8);
        const nodes: GraphNode[] = rawNodes.map((n: any, i: number) => {
          const angle = (2 * Math.PI * i) / rawNodes.length;
          const jitter = (Math.random() - 0.5) * radius * 0.4;
          const baseSize = n.type === "category" ? 18 : n.type === "episode" ? 16 : n.type === "profile" ? 14 : n.type === "memory" ? 10 : n.type === "fact" ? 7 : n.type === "scene" ? 4 : 6;
          return {
            ...n,
            x: cx + Math.cos(angle) * radius + jitter,
            y: cy + Math.sin(angle) * radius + jitter,
            vx: 0,
            vy: 0,
            size: baseSize * (0.6 + (n.importance || 0.5) * 0.8),
          };
        });

        nodesRef.current = nodes;
        edgesRef.current = rawEdges;
        setStats(data.stats);
        setLoading(false);
      } catch (e: any) {
        if (!cancelled) {
          setError(e.message || "Failed to load graph");
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  /* ── Force simulation + render loop ── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let running = true;
    let tick = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.parentElement!.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = rect.width + "px";
      canvas.style.height = rect.height + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const simulate = () => {
      if (!running) return;
      const nodes = nodesRef.current;
      const edges = edgesRef.current;
      if (nodes.length === 0) { frameRef.current = requestAnimationFrame(simulate); return; }

      tick++;
      const cooling = Math.max(0.01, 1 - tick / 600);

      // ── Forces ──
      // Spatial Hash Repulsion for large graphs
      const cellSize = 100;
      const grid = new Map<string, GraphNode[]>();
      for (const n of nodes) {
        const gx = Math.floor(n.x / cellSize);
        const gy = Math.floor(n.y / cellSize);
        const key = `${gx},${gy}`;
        let cell = grid.get(key);
        if (!cell) { cell = []; grid.set(key, cell); }
        cell.push(n);
      }

      for (const n1 of nodes) {
        const gx = Math.floor(n1.x / cellSize);
        const gy = Math.floor(n1.y / cellSize);
        for (let dx = -1; dx <= 1; dx++) {
          for (let dy = -1; dy <= 1; dy++) {
            const key = `${gx + dx},${gy + dy}`;
            const cell = grid.get(key);
            if (!cell) continue;
            for (const n2 of cell) {
              if (n1 === n2) continue;
              const dX = n2.x - n1.x;
              const dY = n2.y - n1.y;
              const distSq = dX * dX + dY * dY + 0.1;
              if (distSq < cellSize * cellSize) {
                const dist = Math.sqrt(distSq);
                const repulse = 800 / distSq;
                const fx = (dX / dist) * repulse * cooling;
                const fy = (dY / dist) * repulse * cooling;
                n1.vx -= fx;
                n1.vy -= fy;
              }
            }
          }
        }
      }

      // Attraction along edges
      for (const e of edges) {
        const src = nodes[e.source];
        const tgt = nodes[e.target];
        if (!src || !tgt) continue;
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.1;
        const spring = dist * 0.003 * cooling;
        const fx = (dx / dist) * spring;
        const fy = (dy / dist) * spring;
        src.vx += fx;
        src.vy += fy;
        tgt.vx -= fx;
        tgt.vy -= fy;
      }

      // Centering force
      for (const n of nodes) {
        n.vx -= n.x * 0.0005;
        n.vy -= n.y * 0.0005;
      }

      // Velocity integration + damping
      for (const n of nodes) {
        n.vx *= 0.85;
        n.vy *= 0.85;
        n.x += n.vx;
        n.y += n.vy;
      }

      // ── Render ──
      const W = canvas.width / (window.devicePixelRatio || 1);
      const H = canvas.height / (window.devicePixelRatio || 1);
      ctx.clearRect(0, 0, W, H);

      // Background
      ctx.fillStyle = "#0a0a0f";
      ctx.fillRect(0, 0, W, H);

      // Subtle grid
      ctx.strokeStyle = "rgba(255,255,255,0.02)";
      ctx.lineWidth = 0.5;
      const gridSize = 60 * zoomRef.current;
      const ox = (W / 2 + panRef.current.x * zoomRef.current) % gridSize;
      const oy = (H / 2 + panRef.current.y * zoomRef.current) % gridSize;
      for (let gx = ox; gx < W; gx += gridSize) { ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke(); }
      for (let gy = oy; gy < H; gy += gridSize) { ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke(); }

      ctx.save();
      ctx.translate(W / 2 + panRef.current.x * zoomRef.current, H / 2 + panRef.current.y * zoomRef.current);
      ctx.scale(zoomRef.current, zoomRef.current);

      // Draw edges
      for (const e of edges) {
        const src = nodes[e.source];
        const tgt = nodes[e.target];
        if (!src || !tgt) continue;
        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        ctx.lineTo(tgt.x, tgt.y);
        ctx.strokeStyle = EDGE_COLORS[e.type] || "rgba(200,200,200,0.08)";
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }

      // Draw nodes
      let hoveredNode: GraphNode | null = null;
      const invZ = 1 / zoomRef.current;
      const mx = (mouseRef.current.x - W / 2 - panRef.current.x * zoomRef.current) * invZ;
      const my = (mouseRef.current.y - H / 2 - panRef.current.y * zoomRef.current) * invZ;

      for (const n of nodes) {
        const color = TYPE_COLORS[n.type] || "#888";
        const glow = TYPE_GLOW[n.type] || "rgba(128,128,128,0.2)";
        const pulse = 1 + Math.sin(tick * 0.03 + n.x * 0.01) * 0.08;
        const r = n.size * pulse;

        // Glow
        ctx.beginPath();
        ctx.arc(n.x, n.y, r * 2.5, 0, Math.PI * 2);
        ctx.fillStyle = glow;
        ctx.fill();

        // Core
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Bright center
        ctx.beginPath();
        ctx.arc(n.x, n.y, r * 0.4, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,255,255,0.6)";
        ctx.fill();

        // Hit test for hover
        const dx = mx - n.x, dy = my - n.y;
        if (dx * dx + dy * dy < (r + 8) * (r + 8)) {
          hoveredNode = n;
        }
      }

      // Draw labels for category nodes always
      ctx.font = "bold 9px 'Inter', system-ui, sans-serif";
      ctx.textAlign = "center";
      for (const n of nodes) {
        if (n.type === "category") {
          ctx.fillStyle = "rgba(167,139,250,0.9)";
          ctx.fillText(n.label, n.x, n.y - n.size - 6);
        }
      }

      ctx.restore();

      // Hover tooltip
      if (hoveredNode) {
        setHovered(hoveredNode);
      } else {
        setHovered(null);
      }

      frameRef.current = requestAnimationFrame(simulate);
    };

    frameRef.current = requestAnimationFrame(simulate);

    return () => {
      running = false;
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [loading]);

  /* ── Mouse handlers ── */
  const onMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    if (panRef.current.dragging) {
      panRef.current.x = panRef.current.panStartX + (e.clientX - panRef.current.startX) / zoomRef.current;
      panRef.current.y = panRef.current.panStartY + (e.clientY - panRef.current.startY) / zoomRef.current;
    }
  };
  const onMouseDown = (e: React.MouseEvent) => {
    panRef.current.dragging = true;
    panRef.current.startX = e.clientX;
    panRef.current.startY = e.clientY;
    panRef.current.panStartX = panRef.current.x;
    panRef.current.panStartY = panRef.current.y;
  };
  const onMouseUp = () => { panRef.current.dragging = false; };
  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    zoomRef.current = Math.max(0.1, Math.min(5, zoomRef.current * delta));
  };

  return (
    <div style={{ width: "100%", height: "100%", position: "relative", background: "#0a0a0f", overflow: "hidden" }}>
      {/* Header Stats Bar */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 40,
        background: "linear-gradient(180deg, rgba(10,10,15,0.95) 0%, rgba(10,10,15,0) 100%)",
        display: "flex", alignItems: "center", gap: 20, padding: "0 16px",
        fontFamily: "'Inter', system-ui, sans-serif", fontSize: 11, zIndex: 10,
      }}>
        <span style={{ color: "#ff6b35", fontWeight: 700, letterSpacing: "0.08em" }}>◉ MORPHO CORTEX</span>
        {stats && (
          <>
            <span style={{ color: "#666" }}>|</span>
            <span style={{ color: TYPE_COLORS.memory }}>● {stats.memories} mems</span>
            <span style={{ color: TYPE_COLORS.scene }}>● {stats.scenes} scenes</span>
            <span style={{ color: TYPE_COLORS.episode }}>● {stats.episodes} eps</span>
            <span style={{ color: TYPE_COLORS.profile }}>● {stats.profiles} profs</span>
            <span style={{ color: TYPE_COLORS.entity }}>● {stats.entities} ents</span>
            <span style={{ color: TYPE_COLORS.category }}>● {stats.categories} cats</span>
            <span style={{ color: TYPE_COLORS.fact }}>● {stats.facts} facts</span>
            <span style={{ color: "#666" }}>|</span>
            <span style={{ color: "#555" }}>{stats.edge_count} edges</span>
          </>
        )}
      </div>

      {/* Loading / Error */}
      {loading && (
        <div style={{
          position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
          color: "#ff6b35", fontFamily: "monospace", fontSize: 14, zIndex: 20,
        }}>
          <span style={{ animation: "pulse 1.5s infinite" }}>◉ Loading neural graph from Dhee memory...</span>
        </div>
      )}
      {error && (
        <div style={{
          position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
          color: "#ef4444", fontFamily: "monospace", fontSize: 13, zIndex: 20,
        }}>
          Error: {error}
        </div>
      )}

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: "100%", display: "block", cursor: panRef.current.dragging ? "grabbing" : "grab" }}
        onMouseMove={onMouseMove}
        onMouseDown={onMouseDown}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        onWheel={onWheel}
      />

      {/* Hover tooltip */}
      {hovered && (
        <div style={{
          position: "absolute",
          left: mouseRef.current.x + 14,
          top: mouseRef.current.y - 10,
          background: "rgba(15,15,20,0.95)",
          border: `1px solid ${TYPE_COLORS[hovered.type] || "#444"}`,
          borderRadius: 8,
          padding: "8px 12px",
          maxWidth: 320,
          fontFamily: "'Inter', system-ui, sans-serif",
          fontSize: 11,
          color: "#ddd",
          zIndex: 30,
          pointerEvents: "none",
          boxShadow: `0 0 20px ${TYPE_GLOW[hovered.type] || "rgba(0,0,0,0.5)"}`,
        }}>
          <div style={{ color: TYPE_COLORS[hovered.type], fontWeight: 700, fontSize: 10, letterSpacing: "0.06em", marginBottom: 4 }}>
            {hovered.type.toUpperCase()}{hovered.subtype ? ` · ${hovered.subtype}` : ""}
          </div>
          <div style={{ lineHeight: 1.4, wordBreak: "break-word" }}>{hovered.label}</div>
          <div style={{ marginTop: 4, color: "#666", fontSize: 10 }}>
            strength: {hovered.strength.toFixed(2)} · importance: {hovered.importance.toFixed(2)}
          </div>
        </div>
      )}

      {/* Legend */}
      <div style={{
        position: "absolute", bottom: 12, right: 16,
        display: "flex", gap: 14, fontFamily: "'Inter', system-ui", fontSize: 10, color: "#555", zIndex: 10,
      }}>
        {Object.entries(TYPE_COLORS).map(([t, c]) => (
          <span key={t} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: c, display: "inline-block" }} />
            {t}
          </span>
        ))}
      </div>
    </div>
  );
};
