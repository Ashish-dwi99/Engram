"""Binary adapter for MorphoHDL integration.

Translates Dhee KnowledgeGraph data into binary Struct-of-Arrays (SoA) layout.
"""

import struct
from typing import Any, Dict
from dhee.core.graph import KnowledgeGraph


class MorphoBinaryAdapter:
    """Translates Dhee graphs to binary buffers for Morpho."""

    @staticmethod
    def compile_graph_to_binary(graph: KnowledgeGraph, memory_id: str) -> bytes:
        """Convert a local neighborhood into a flat binary SoA buffer.
        
        Format:
        [Header]
        - node_count: int32 (little endian)
        - edge_count: int32 (little endian)
        
        [Node SoA]
        - node_ids: int32[] (hash of string IDs)
        - node_types: int32[] (hash of string types)
        - node_depths: float32[]
        
        [Edge SoA]
        - edge_sources: int32[] (node index)
        - edge_targets: int32[] (node index)
        - edge_weights: float32[]
        """
        if memory_id == "all":
            nodes = []
            edges = []
            memories = set()
            for rel in graph.relationships:
                memories.add(rel.source_id)
                memories.add(rel.target_id)
                edges.append({
                    "source": rel.source_id,
                    "target": rel.target_id,
                    "type": rel.relation_type.value,
                    "weight": rel.weight
                })
            for mid in graph.memory_entities.keys():
                memories.add(mid)
            for mid in memories:
                nodes.append({"id": mid, "type": "memory", "depth": 0})
            for entity_name, entity in graph.entities.items():
                nodes.append({
                    "id": f"entity:{entity_name}",
                    "type": "entity",
                    "depth": 0
                })
                # Add implicit has_entity edges
                for mid in entity.memory_ids:
                    edges.append({
                        "source": mid,
                        "target": f"entity:{entity_name}",
                        "type": "has_entity",
                        "weight": 1.0
                    })
        else:
            dhee_graph = graph.get_memory_graph(memory_id)
            nodes = dhee_graph.get("nodes", [])
            edges = dhee_graph.get("edges", [])

        node_count = len(nodes)
        edge_count = len(edges)
        
        id_to_index = {}
        
        node_ids = []
        node_types = []
        node_depths = []
        
        for i, node in enumerate(nodes):
            nid = node["id"]
            ntype = node.get("type", "unknown")
            id_to_index[nid] = i
            
            # Simple 32-bit int hash
            node_ids.append(hash(nid) & 0xFFFFFFFF)
            node_types.append(hash(ntype) & 0xFFFFFFFF)
            node_depths.append(float(node.get("depth", 0)))
            
        edge_sources = []
        edge_targets = []
        edge_weights = []
        
        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            if src in id_to_index and tgt in id_to_index:
                edge_sources.append(id_to_index[src])
                edge_targets.append(id_to_index[tgt])
                edge_weights.append(float(edge.get("weight", 1.0)))
                
        actual_edge_count = len(edge_sources)
        
        # Header (8 bytes)
        buffer = bytearray(struct.pack("<ii", node_count, actual_edge_count))
        
        # Node Arrays
        if node_count > 0:
            # Use 'i' for signed 32-bit or 'I' for unsigned 32-bit. We use 'I' since we mask with 0xFFFFFFFF.
            buffer.extend(struct.pack(f"<{node_count}I", *node_ids))
            buffer.extend(struct.pack(f"<{node_count}I", *node_types))
            buffer.extend(struct.pack(f"<{node_count}f", *node_depths))
            
        # Edge Arrays
        if actual_edge_count > 0:
            buffer.extend(struct.pack(f"<{actual_edge_count}i", *edge_sources))
            buffer.extend(struct.pack(f"<{actual_edge_count}i", *edge_targets))
            buffer.extend(struct.pack(f"<{actual_edge_count}f", *edge_weights))
            
        return bytes(buffer)
