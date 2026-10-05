// Radial React Flow layout builder for extracted P&ID topology.
import type { Node, Edge } from "@xyflow/react";
import type { TopologyGraph } from "@/lib/types";
import { arrowMarker, type CanvasTokens } from "@/lib/graph-theme";


const CENTER_TYPES = new Set(["Pump", "Vessel", "Separator", "Equipment"]);
const EDGE_TYPE_TOKENS: Record<string, keyof CanvasTokens> = {
  flow_connection: "--accent",
  instrumentation_loop: "--caution",
};

export function buildLayout(topo: TopologyGraph, tokens: CanvasTokens): { nodes: Node[]; edges: Edge[] } {
  const center = topo.nodes.find((n) => CENTER_TYPES.has(n.node_type)) ?? topo.nodes[0];
  const others = topo.nodes.filter((n) => n.node_id !== center.node_id);

  const rfNodes: Node[] = [
    { id: center.node_id, type: "topo", position: { x: 0, y: 0 }, data: center as unknown as Record<string, unknown>, draggable: true },
    ...others.map((n, i) => {
      const angle = (i / (others.length || 1)) * 2 * Math.PI - Math.PI / 2;
      const r = 280;
      return {
        id: n.node_id,
        type: "topo",
        position: { x: Math.cos(angle) * r, y: Math.sin(angle) * r },
        data: n as unknown as Record<string, unknown>,
        draggable: true,
      };
    }),
  ];

  const rfEdges: Edge[] = topo.edges.map((e) => {
    const color = tokens[EDGE_TYPE_TOKENS[e.edge_type] ?? "--muted"];
    const isLoop = e.edge_type === "instrumentation_loop";
    return {
      id: e.edge_id,
      type: "floating",
      source: e.source_id,
      target: e.target_id,
      label: e.label,
      style: { stroke: color, strokeWidth: isLoop ? 1.2 : 1.8, strokeDasharray: isLoop ? "4,3" : undefined },
      markerEnd: arrowMarker(color, 12),
    };
  });

  return { nodes: rfNodes, edges: rfEdges };
}
