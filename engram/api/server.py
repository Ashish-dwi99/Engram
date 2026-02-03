"""Engram REST API Server.

FastAPI-based HTTP server for the Engram memory layer.
Provides a standard REST interface for memory operations.

Usage:
    engram-api                    # Start server on default port 8100
    engram-api --port 8080        # Custom port
    engram-api --host 0.0.0.0     # Bind to all interfaces
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engram import Memory, MemoryConfig
from engram.exceptions import FadeMemValidationError
from engram.observability import metrics, logger as structured_logger, add_metrics_routes

logger = logging.getLogger(__name__)

# API Models
class AddMemoryRequest(BaseModel):
    """Request model for adding memories."""
    content: Optional[str] = Field(default=None, description="Memory content to store")
    messages: Optional[Union[str, List[Dict[str, Any]]]] = Field(
        default=None,
        description="Alias for content or a list of chat messages",
    )
    user_id: Optional[str] = Field(default="default", description="User identifier")
    agent_id: Optional[str] = Field(default=None, description="Agent identifier")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    categories: Optional[List[str]] = Field(default=None, description="Category tags")
    agent_category: Optional[str] = Field(default=None, description="Agent category for scope sharing")
    connector_id: Optional[str] = Field(default=None, description="Connector identifier for scope sharing")
    scope: Optional[str] = Field(default=None, description="Memory scope (agent|connector|category|global)")
    source_app: Optional[str] = Field(default=None, description="Source application identifier")
    infer: bool = Field(default=True, description="Whether to extract facts from content")


class SearchRequest(BaseModel):
    """Request model for searching memories."""
    query: str = Field(..., description="Search query")
    user_id: Optional[str] = Field(default="default", description="User identifier")
    agent_id: Optional[str] = Field(default=None, description="Agent identifier")
    agent_category: Optional[str] = Field(default=None, description="Agent category for scope sharing")
    limit: int = Field(default=10, ge=1, le=100, description="Max results to return")
    categories: Optional[List[str]] = Field(default=None, description="Filter by categories")
    connector_ids: Optional[List[str]] = Field(default=None, description="Connector IDs to include")
    scope_filter: Optional[List[str]] = Field(default=None, description="Restrict to specific scopes")
    scope: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Alias for scope_filter (agent|connector|category|global)",
    )


class UpdateMemoryRequest(BaseModel):
    """Request model for updating a memory."""
    content: Optional[str] = Field(default=None, description="New content")
    data: Optional[str] = Field(default=None, description="Alias for content")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadata to merge")


class DecayRequest(BaseModel):
    """Request model for applying decay."""
    user_id: Optional[str] = Field(default=None, description="Scope to specific user")
    agent_id: Optional[str] = Field(default=None, description="Scope to specific agent")
    dry_run: bool = Field(default=False, description="Preview without applying changes")


class MemoryResponse(BaseModel):
    """Response model for a single memory."""
    id: str
    content: str
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    categories: List[str] = Field(default_factory=list)
    layer: str = "sml"
    strength: float = 1.0
    created_at: Optional[str] = None


class SearchResultResponse(BaseModel):
    """Response model for search results."""
    results: List[Dict[str, Any]]
    count: int


class StatsResponse(BaseModel):
    """Response model for memory statistics."""
    total_memories: int
    sml_count: int
    lml_count: int
    categories: Dict[str, int]
    storage_mb: Optional[float] = None


class DecayResponse(BaseModel):
    """Response model for decay operation."""
    decayed: int
    forgotten: int
    promoted: int
    dry_run: bool


# Initialize FastAPI app
app = FastAPI(
    title="Engram API",
    description="Bio-inspired memory layer for AI agents with forgetting, echo encoding, and dynamic categories",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add metrics endpoints (/metrics, /metrics/json)
add_metrics_routes(app)

# Global memory instance (initialized on startup)
_memory: Optional[Memory] = None


def get_memory() -> Memory:
    """Get or create the global Memory instance."""
    global _memory
    if _memory is None:
        _memory = Memory()
    return _memory


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "engram"}


@app.get("/v1/version")
async def get_version():
    """Get API version."""
    from engram import __version__
    return {"version": __version__, "api_version": "v1"}


# Memory CRUD operations
@app.post("/v1/memories", response_model=Dict[str, Any])
@app.post("/v1/memories/", response_model=Dict[str, Any])
async def add_memory(request: AddMemoryRequest):
    """Add a new memory.

    Stores content with optional metadata and categories.
    If infer=True (default), extracts facts from the content.
    """
    with metrics.measure("api_add", user_id=request.user_id):
        try:
            memory = get_memory()
            messages = request.content if request.content is not None else request.messages
            if messages is None:
                raise HTTPException(status_code=400, detail="content or messages is required")
            result = memory.add(
                messages=messages,
                user_id=request.user_id,
                agent_id=request.agent_id,
                metadata=request.metadata,
                categories=request.categories,
                agent_category=request.agent_category,
                connector_id=request.connector_id,
                scope=request.scope,
                source_app=request.source_app,
                infer=request.infer,
            )
            metrics.record_add(0, count=len(result.get("results", [1])))
            return result
        except Exception as e:
            logger.error(f"Error adding memory: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/memories", response_model=Dict[str, Any])
@app.get("/v1/memories/", response_model=Dict[str, Any])
async def list_memories(
    user_id: str = Query(default="default", description="User identifier"),
    agent_id: Optional[str] = Query(default=None, description="Agent identifier"),
    layer: Optional[str] = Query(default=None, description="Filter by layer (sml/lml)"),
    limit: int = Query(default=50, ge=1, le=500, description="Max results"),
):
    """List all memories for a user/agent."""
    try:
        memory = get_memory()
        payload = memory.get_all(
            user_id=user_id,
            agent_id=agent_id,
            layer=layer,
            limit=limit,
        )
        memories = payload.get("results", payload) if isinstance(payload, dict) else payload
        return {"memories": memories, "count": len(memories)}
    except Exception as e:
        logger.error(f"Error listing memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/memories/{memory_id}", response_model=Dict[str, Any])
@app.get("/v1/memories/{memory_id}/", response_model=Dict[str, Any])
async def get_memory_by_id(memory_id: str):
    """Get a specific memory by ID."""
    try:
        memory = get_memory()
        result = memory.get(memory_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/v1/memories/{memory_id}", response_model=Dict[str, Any])
@app.put("/v1/memories/{memory_id}/", response_model=Dict[str, Any])
async def update_memory(memory_id: str, request: UpdateMemoryRequest):
    """Update an existing memory."""
    try:
        memory = get_memory()
        update_data = {}
        content = request.content if request.content is not None else request.data
        if content is not None:
            update_data["content"] = content
        if request.metadata is not None:
            update_data["metadata"] = request.metadata

        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")

        result = memory.update(memory_id, update_data)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/v1/memories/{memory_id}")
@app.delete("/v1/memories/{memory_id}/")
async def delete_memory(memory_id: str):
    """Delete a memory by ID."""
    try:
        memory = get_memory()
        memory.delete(memory_id)
        return {"status": "deleted", "id": memory_id}
    except Exception as e:
        logger.error(f"Error deleting memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/v1/memories", response_model=Dict[str, Any])
@app.delete("/v1/memories/", response_model=Dict[str, Any])
async def delete_memories(
    user_id: Optional[str] = Query(default=None, description="User identifier"),
    agent_id: Optional[str] = Query(default=None, description="Agent identifier"),
    run_id: Optional[str] = Query(default=None, description="Run identifier"),
    app_id: Optional[str] = Query(default=None, description="App identifier"),
):
    """Delete all memories matching filters."""
    try:
        memory = get_memory()
        result = memory.delete_all(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            app_id=app_id,
        )
        return result
    except FadeMemValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error deleting memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/memories/{memory_id}/history", response_model=List[Dict[str, Any]])
@app.get("/v1/memories/{memory_id}/history/", response_model=List[Dict[str, Any]])
async def get_memory_history(memory_id: str):
    """Get history for a specific memory."""
    try:
        memory = get_memory()
        return memory.history(memory_id)
    except Exception as e:
        logger.error(f"Error getting memory history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Search
@app.post("/v1/search", response_model=SearchResultResponse)
@app.post("/v1/search/", response_model=SearchResultResponse)
@app.post("/v1/memories/search", response_model=SearchResultResponse)
@app.post("/v1/memories/search/", response_model=SearchResultResponse)
async def search_memories(request: SearchRequest):
    """Search memories using semantic similarity.

    Uses vector search with optional category filtering.
    Results are ranked by composite score (similarity * strength).
    """
    with metrics.measure("api_search", user_id=request.user_id):
        try:
            memory = get_memory()
            payload = memory.search(
                query=request.query,
                user_id=request.user_id,
                agent_id=request.agent_id,
                limit=request.limit,
                categories=request.categories,
                agent_category=request.agent_category,
                connector_ids=request.connector_ids,
                scope_filter=request.scope_filter or request.scope,
            )
            results = payload.get("results", payload) if isinstance(payload, dict) else payload
            metrics.record_search(0, results_count=len(results))
            return SearchResultResponse(
                results=results,
                count=len(results),
            )
        except Exception as e:
            logger.error(f"Error searching memories: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# Decay operations
@app.post("/v1/decay", response_model=DecayResponse)
async def apply_decay(request: DecayRequest):
    """Apply memory decay (forgetting).

    Uses Ebbinghaus curve to decay memory strength.
    Memories below threshold are forgotten.
    High-access memories may be promoted to long-term.
    """
    try:
        memory = get_memory()

        if request.dry_run:
            # TODO: Implement dry-run preview
            return DecayResponse(decayed=0, forgotten=0, promoted=0, dry_run=True)

        result = memory.apply_decay(
            user_id=request.user_id,
            agent_id=request.agent_id,
        )
        return DecayResponse(
            decayed=result.get("decayed", 0),
            forgotten=result.get("forgotten", 0),
            promoted=result.get("promoted", 0),
            dry_run=False,
        )
    except Exception as e:
        logger.error(f"Error applying decay: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Statistics
@app.get("/v1/stats", response_model=StatsResponse)
async def get_stats(
    user_id: Optional[str] = Query(default=None, description="Filter by user"),
    agent_id: Optional[str] = Query(default=None, description="Filter by agent"),
):
    """Get memory statistics."""
    try:
        memory = get_memory()
        stats = memory.get_stats(user_id=user_id, agent_id=agent_id)
        return StatsResponse(
            total_memories=stats.get("total", 0),
            sml_count=stats.get("sml_count", 0),
            lml_count=stats.get("lml_count", 0),
            categories=stats.get("categories", {}),
            storage_mb=stats.get("storage_mb"),
        )
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Category operations
@app.get("/v1/categories")
async def list_categories():
    """List all categories with hierarchy."""
    try:
        memory = get_memory()
        categories = memory.get_categories()
        return {"categories": categories}
    except Exception as e:
        logger.error(f"Error listing categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/categories/tree")
async def get_category_tree():
    """Get category tree structure."""
    try:
        memory = get_memory()
        tree = memory.get_category_tree()
        return {"tree": tree}
    except Exception as e:
        logger.error(f"Error getting category tree: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/categories/{category_id}/summary")
async def get_category_summary(
    category_id: str,
    regenerate: bool = Query(default=False, description="Force regenerate summary"),
):
    """Get AI-generated summary for a category."""
    try:
        memory = get_memory()
        summary = memory.get_category_summary(category_id, regenerate=regenerate)
        return {"category_id": category_id, "summary": summary}
    except Exception as e:
        logger.error(f"Error getting category summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def run():
    """Run the Engram API server."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Engram REST API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8100, help="Port to listen on")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    print(f"Starting Engram API server on http://{args.host}:{args.port}")
    print(f"API docs available at http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "engram.api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    run()
