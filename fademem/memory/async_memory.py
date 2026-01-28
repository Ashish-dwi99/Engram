import asyncio
from typing import Any, Dict, List, Optional, Union

from fadem.configs.base import MemoryConfig
from fadem.memory.main import Memory


class AsyncMemory:
    def __init__(self, config: Optional[MemoryConfig] = None):
        self._sync = Memory(config=config)

    @classmethod
    async def from_config(cls, config_dict: Dict[str, Any]):
        return cls(MemoryConfig(**config_dict))

    async def add(self, messages, **kwargs):
        return await asyncio.to_thread(self._sync.add, messages, **kwargs)

    async def search(self, query: str, **kwargs):
        return await asyncio.to_thread(self._sync.search, query, **kwargs)

    async def get(self, memory_id: str):
        return await asyncio.to_thread(self._sync.get, memory_id)

    async def get_all(self, **kwargs):
        return await asyncio.to_thread(self._sync.get_all, **kwargs)

    async def update(self, memory_id: str, data: str):
        return await asyncio.to_thread(self._sync.update, memory_id, data)

    async def delete(self, memory_id: str):
        return await asyncio.to_thread(self._sync.delete, memory_id)

    async def delete_all(self, **kwargs):
        return await asyncio.to_thread(self._sync.delete_all, **kwargs)

    async def history(self, memory_id: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync.history, memory_id)

    async def reset(self):
        return await asyncio.to_thread(self._sync.reset)

    # FadeMem extras
    async def apply_decay(self, scope: Dict[str, Any] = None):
        return await asyncio.to_thread(self._sync.apply_decay, scope)

    async def fuse_memories(self, memory_ids: List[str], user_id: str = None):
        return await asyncio.to_thread(self._sync.fuse_memories, memory_ids, user_id)

    async def get_stats(self, user_id: str = None):
        return await asyncio.to_thread(self._sync.get_stats, user_id)

    async def promote(self, memory_id: str):
        return await asyncio.to_thread(self._sync.promote, memory_id)

    async def demote(self, memory_id: str):
        return await asyncio.to_thread(self._sync.demote, memory_id)
