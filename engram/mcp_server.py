"""
engram MCP Server for Claude Code integration.

This server exposes engram's memory capabilities as MCP tools that Claude Code can use.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from engram.memory.main import Memory
from engram.configs.base import (
    MemoryConfig,
    VectorStoreConfig,
    LLMConfig,
    EmbedderConfig,
    FadeMemConfig,
)


def _get_embedding_dims_for_model(model: str, provider: str) -> int:
    """Get the embedding dimensions for a given model."""
    # Known embedding model dimensions
    EMBEDDING_DIMS = {
        # Gemini models
        "models/text-embedding-005": 768,
        "text-embedding-005": 768,
        "models/text-embedding-004": 768,
        "text-embedding-004": 768,
        "gemini-embedding-001": 3072,
        # OpenAI models
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    # Check for explicit env var override first
    env_dims = os.environ.get("FADEM_EMBEDDING_DIMS")
    if env_dims:
        return int(env_dims)

    # Look up known dimensions
    if model in EMBEDDING_DIMS:
        return EMBEDDING_DIMS[model]

    # Default based on provider (using latest model defaults)
    if provider == "gemini":
        return 3072  # gemini-embedding-001 default
    elif provider == "openai":
        return 1536
    return 3072


def get_memory_instance() -> Memory:
    """Create and return a configured Memory instance."""
    # Check for API keys in environment
    gemini_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    # Determine LLM and embedder provider based on available keys
    if gemini_key:
        embedder_model = os.environ.get("FADEM_EMBEDDER_MODEL", "gemini-embedding-001")
        embedding_dims = _get_embedding_dims_for_model(embedder_model, "gemini")

        llm_config = LLMConfig(
            provider="gemini",
            config={
                "model": os.environ.get("FADEM_LLM_MODEL", "gemini-2.0-flash"),
                "temperature": 0.1,
                "max_tokens": 1024,
                "api_key": gemini_key,
            }
        )
        embedder_config = EmbedderConfig(
            provider="gemini",
            config={
                "model": embedder_model,
                "api_key": gemini_key,
            }
        )
    elif openai_key:
        embedder_model = os.environ.get("FADEM_EMBEDDER_MODEL", "text-embedding-3-small")
        embedding_dims = _get_embedding_dims_for_model(embedder_model, "openai")

        llm_config = LLMConfig(
            provider="openai",
            config={
                "model": os.environ.get("FADEM_LLM_MODEL", "gpt-4o-mini"),
                "temperature": 0.1,
                "max_tokens": 1024,
                "api_key": openai_key,
            }
        )
        embedder_config = EmbedderConfig(
            provider="openai",
            config={
                "model": embedder_model,
                "api_key": openai_key,
            }
        )
    else:
        raise RuntimeError(
            "No API key found. Set GOOGLE_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY environment variable."
        )

    # Configure vector store
    qdrant_path = os.environ.get(
        "FADEM_QDRANT_PATH",
        os.path.join(os.path.expanduser("~"), ".engram", "qdrant")
    )
    vector_store_config = VectorStoreConfig(
        provider="qdrant",
        config={
            "path": qdrant_path,
            "collection_name": os.environ.get("FADEM_COLLECTION", "fadem_memories"),
            "embedding_model_dims": embedding_dims,
        }
    )

    # Configure history database
    history_db_path = os.environ.get(
        "FADEM_HISTORY_DB",
        os.path.join(os.path.expanduser("~"), ".engram", "history.db")
    )

    # engram-specific settings
    fadem_config = FadeMemConfig(
        enable_forgetting=os.environ.get("FADEM_ENABLE_FORGETTING", "true").lower() == "true",
        sml_decay_rate=float(os.environ.get("FADEM_SML_DECAY_RATE", "0.15")),
        lml_decay_rate=float(os.environ.get("FADEM_LML_DECAY_RATE", "0.02")),
    )

    config = MemoryConfig(
        vector_store=vector_store_config,
        llm=llm_config,
        embedder=embedder_config,
        history_db_path=history_db_path,
        embedding_model_dims=embedding_dims,
        engram=fadem_config,
    )

    return Memory(config)


# Global memory instance (lazy initialized)
_memory: Optional[Memory] = None


def get_memory() -> Memory:
    """Get or create the global memory instance."""
    global _memory
    if _memory is None:
        _memory = get_memory_instance()
    return _memory


# Create the MCP server
server = Server("engram-memory")


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available engram tools."""
    return [
        Tool(
            name="add_memory",
            description="Add a new memory to engram. Use this to remember important facts, preferences, or context about the user or conversation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The memory content to store. Can be a fact, preference, or any important information."
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User identifier to scope this memory to (default: 'default')"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier to scope this memory to (optional)"
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional categories to tag this memory with (e.g., ['preferences', 'personal'])"
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata to attach to the memory"
                    },
                    "agent_category": {
                        "type": "string",
                        "description": "Agent category for scope sharing (e.g. 'coding')"
                    },
                    "connector_id": {
                        "type": "string",
                        "description": "Connector identifier for scope sharing (e.g. 'github')"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Memory scope: agent|connector|category|global"
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="search_memory",
            description="Search engram for relevant memories. Use this to recall information about the user, previous conversations, or stored context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query - what you're trying to remember"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User identifier to search memories for (default: 'default')"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier to scope search to (optional)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)"
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter results by categories"
                    },
                    "agent_category": {
                        "type": "string",
                        "description": "Agent category for scope sharing"
                    },
                    "connector_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Connector IDs to include for connector-scope memories"
                    },
                    "scope_filter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Restrict results to specific scopes"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_all_memories",
            description="Get all stored memories for a user. Useful for reviewing what's been remembered.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier (default: 'default')"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier to scope results to (optional)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of memories to return (default: 50)"
                    },
                    "layer": {
                        "type": "string",
                        "enum": ["sml", "lml"],
                        "description": "Filter by memory layer: 'sml' (short-term) or 'lml' (long-term)"
                    }
                }
            }
        ),
        Tool(
            name="get_memory",
            description="Get a specific memory by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The ID of the memory to retrieve"
                    }
                },
                "required": ["memory_id"]
            }
        ),
        Tool(
            name="update_memory",
            description="Update an existing memory's content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The ID of the memory to update"
                    },
                    "content": {
                        "type": "string",
                        "description": "The new content for the memory"
                    }
                },
                "required": ["memory_id", "content"]
            }
        ),
        Tool(
            name="delete_memory",
            description="Delete a specific memory by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The ID of the memory to delete"
                    }
                },
                "required": ["memory_id"]
            }
        ),
        Tool(
            name="get_memory_stats",
            description="Get statistics about stored memories including counts and layer distribution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier to get stats for (default: all users)"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier to scope stats to (optional)"
                    }
                }
            }
        ),
        Tool(
            name="apply_memory_decay",
            description="Apply memory decay algorithm to reduce strength of old, unused memories. This simulates natural forgetting.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier to apply decay for (default: all users)"
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Agent identifier to apply decay for (optional)"
                    }
                }
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    try:
        memory = get_memory()
        result: Any = None

        if name == "add_memory":
            content = arguments.get("content", "")
            user_id = arguments.get("user_id", "default")
            agent_id = arguments.get("agent_id")
            categories = arguments.get("categories")
            metadata = arguments.get("metadata")
            agent_category = arguments.get("agent_category")
            connector_id = arguments.get("connector_id")
            scope = arguments.get("scope")

            result = memory.add(
                messages=content,
                user_id=user_id,
                agent_id=agent_id,
                categories=categories,
                metadata=metadata,
                agent_category=agent_category,
                connector_id=connector_id,
                scope=scope,
                infer=False,  # Store the content directly without LLM extraction
            )

        elif name == "search_memory":
            query = arguments.get("query", "")
            user_id = arguments.get("user_id", "default")
            agent_id = arguments.get("agent_id")
            limit = arguments.get("limit", 10)
            categories = arguments.get("categories")
            agent_category = arguments.get("agent_category")
            connector_ids = arguments.get("connector_ids")
            scope_filter = arguments.get("scope_filter")

            result = memory.search(
                query=query,
                user_id=user_id,
                agent_id=agent_id,
                limit=limit,
                categories=categories,
                agent_category=agent_category,
                connector_ids=connector_ids,
                scope_filter=scope_filter,
            )
            # Simplify results for readability
            if "results" in result:
                result["results"] = [
                    {
                        "id": r["id"],
                        "memory": r["memory"],
                        "score": round(r.get("composite_score", r.get("score", 0)), 3),
                        "layer": r.get("layer", "sml"),
                        "categories": r.get("categories", []),
                        "scope": r.get("scope"),
                        "agent_category": r.get("agent_category"),
                        "connector_id": r.get("connector_id"),
                    }
                    for r in result["results"]
                ]

        elif name == "get_all_memories":
            user_id = arguments.get("user_id", "default")
            agent_id = arguments.get("agent_id")
            limit = arguments.get("limit", 50)
            layer = arguments.get("layer")

            result = memory.get_all(
                user_id=user_id,
                agent_id=agent_id,
                limit=limit,
                layer=layer,
            )
            # Simplify results
            if "results" in result:
                result["results"] = [
                    {
                        "id": r["id"],
                        "memory": r["memory"],
                        "layer": r.get("layer", "sml"),
                        "strength": round(r.get("strength", 1.0), 3),
                        "categories": r.get("categories", []),
                    }
                    for r in result["results"]
                ]

        elif name == "get_memory":
            memory_id = arguments.get("memory_id", "")
            result = memory.get(memory_id)
            if result:
                result = {
                    "id": result["id"],
                    "memory": result["memory"],
                    "layer": result.get("layer", "sml"),
                    "strength": round(result.get("strength", 1.0), 3),
                    "categories": result.get("categories", []),
                    "created_at": result.get("created_at"),
                    "access_count": result.get("access_count", 0),
                }
            else:
                result = {"error": "Memory not found"}

        elif name == "update_memory":
            memory_id = arguments.get("memory_id", "")
            content = arguments.get("content", "")
            result = memory.update(memory_id, content)

        elif name == "delete_memory":
            memory_id = arguments.get("memory_id", "")
            result = memory.delete(memory_id)

        elif name == "get_memory_stats":
            user_id = arguments.get("user_id")
            agent_id = arguments.get("agent_id")
            result = memory.get_stats(user_id=user_id, agent_id=agent_id)

        elif name == "apply_memory_decay":
            user_id = arguments.get("user_id")
            agent_id = arguments.get("agent_id")
            scope = {"user_id": user_id, "agent_id": agent_id} if user_id or agent_id else None
            result = memory.apply_decay(scope=scope)

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        error_result = {"error": str(e)}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run():
    """Entry point for the MCP server."""
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    run()
