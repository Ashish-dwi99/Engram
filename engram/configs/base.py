import os
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class VectorStoreConfig(BaseModel):
    provider: str = Field(default="qdrant")
    config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "path": os.path.join(os.path.expanduser("~"), ".engram", "qdrant"),
            "collection_name": "fadem_memories",
        }
    )


class LLMConfig(BaseModel):
    provider: str = Field(default="gemini")
    config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "model": "gemini-2.0-flash",
            "temperature": 0.1,
            "max_tokens": 1024,
        }
    )


class EmbedderConfig(BaseModel):
    provider: str = Field(default="gemini")
    config: Dict[str, Any] = Field(default_factory=lambda: {"model": "gemini-embedding-001"})


class GraphStoreConfig(BaseModel):
    provider: Optional[str] = Field(default=None)
    config: Optional[Dict[str, Any]] = Field(default=None)


class KnowledgeGraphConfig(BaseModel):
    """Configuration for knowledge graph entity extraction and linking."""
    enable_graph: bool = True  # Enable knowledge graph
    use_llm_extraction: bool = False  # Use LLM for entity extraction (slower but more accurate)
    auto_link_entities: bool = True  # Automatically link memories by shared entities
    max_traversal_depth: int = 2  # Maximum depth for graph traversal in search
    graph_boost_weight: float = 0.1  # Boost for graph-related memories in search


class EchoMemConfig(BaseModel):
    """Configuration for EchoMem multi-modal encoding."""
    enable_echo: bool = True
    auto_depth: bool = True  # Auto-detect echo depth based on content importance
    default_depth: str = "medium"  # shallow, medium, deep
    reecho_on_access: bool = False  # Re-process on retrieval (expensive but strengthening)
    reecho_threshold: int = 3  # Re-echo after N accesses
    # Strength multipliers for each depth
    shallow_multiplier: float = 1.0
    medium_multiplier: float = 1.3
    deep_multiplier: float = 1.6
    # Use question_form embedding for primary vector (better query matching)
    use_question_embedding: bool = True


class CategoryMemConfig(BaseModel):
    """
    Configuration for CategoryMem hierarchical category layer.

    Unlike traditional static approaches, CategoryMem provides:
    - Dynamic auto-discovered categories
    - Hierarchical structure with parent/child relationships
    - Category summaries that evolve with memories
    - Category decay (unused categories merge/fade)
    - Category-aware retrieval boosting
    """
    enable_categories: bool = True  # Enable category layer
    auto_categorize: bool = True  # Automatically categorize new memories
    use_llm_categorization: bool = True  # Use LLM for ambiguous categorization

    # Category decay (bio-inspired, like engram)
    enable_category_decay: bool = True
    category_decay_rate: float = 0.05  # Decay rate per cycle
    merge_weak_categories: bool = True  # Merge weak categories automatically
    weak_category_threshold: float = 0.3  # Strength below this triggers merge consideration

    # Summary generation
    auto_generate_summaries: bool = True  # Generate summaries for categories
    summary_update_threshold: int = 5  # Regenerate summary after N new memories

    # Retrieval boosting
    category_boost_weight: float = 0.15  # Boost for matching category in search
    cross_category_boost: float = 0.05  # Boost for related categories

    # Hierarchy
    max_category_depth: int = 3  # Maximum nesting depth
    auto_create_subcategories: bool = True  # Allow dynamic subcategory creation


class SceneConfig(BaseModel):
    """Configuration for episodic scene grouping."""
    enable_scenes: bool = True
    scene_time_gap_minutes: int = 30       # gap > this = new scene
    scene_topic_threshold: float = 0.55    # cosine sim below this = topic shift
    auto_close_inactive_minutes: int = 120
    max_scene_memories: int = 50
    use_llm_summarization: bool = True
    summary_regenerate_threshold: int = 5


class ProfileConfig(BaseModel):
    """Configuration for character profile tracking."""
    enable_profiles: bool = True
    auto_detect_profiles: bool = True
    use_llm_extraction: bool = True
    narrative_regenerate_threshold: int = 10
    self_profile_auto_create: bool = True
    max_facts_per_profile: int = 100


class ScopeConfig(BaseModel):
    """Configuration for scope-aware sharing weights."""
    agent_weight: float = 1.0
    connector_weight: float = 0.97
    category_weight: float = 0.94
    global_weight: float = 0.92


class FadeMemConfig(BaseModel):
    enable_forgetting: bool = True
    sml_decay_rate: float = 0.15
    lml_decay_rate: float = 0.02
    access_dampening_factor: float = 0.5
    promotion_access_threshold: int = 3
    promotion_strength_threshold: float = 0.7
    forgetting_threshold: float = 0.1
    access_strength_boost: float = 0.02
    conflict_similarity_threshold: float = 0.85
    fusion_similarity_threshold: float = 0.90
    enable_fusion: bool = True
    use_tombstone_deletion: bool = True


class MemoryConfig(BaseModel):
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    graph_store: GraphStoreConfig = Field(default_factory=GraphStoreConfig)
    history_db_path: str = Field(
        default_factory=lambda: os.path.join(os.path.expanduser("~"), ".engram", "history.db")
    )
    collection_name: str = "fadem_memories"
    embedding_model_dims: int = 3072  # gemini-embedding-001 default dimensions
    version: str = "v1.3"  # Updated for CategoryMem
    custom_fact_extraction_prompt: Optional[str] = None
    custom_conflict_prompt: Optional[str] = None
    custom_fusion_prompt: Optional[str] = None
    custom_echo_prompt: Optional[str] = None
    custom_category_prompt: Optional[str] = None
    engram: FadeMemConfig = Field(default_factory=FadeMemConfig)
    echo: EchoMemConfig = Field(default_factory=EchoMemConfig)
    category: CategoryMemConfig = Field(default_factory=CategoryMemConfig)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    graph: KnowledgeGraphConfig = Field(default_factory=lambda: KnowledgeGraphConfig())
    scene: SceneConfig = Field(default_factory=SceneConfig)
    profile: ProfileConfig = Field(default_factory=ProfileConfig)
