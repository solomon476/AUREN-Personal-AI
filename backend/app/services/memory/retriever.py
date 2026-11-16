"""Hybrid memory retrieval service integrating lexical and vector similarity."""

import logging
from typing import List, Optional
from uuid import UUID

from app.services.memory.models import MemorySearchResult

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """Retrieves ranked relevant memories for a user query via hybrid search."""

    def __init__(self, repository=None, db_pool=None):
        self._repository = repository
        self._db_pool = db_pool

    async def search_memories(
        self,
        user_id: UUID,
        query_text: str,
        query_embedding: Optional[List[float]] = None,
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> List[MemorySearchResult]:
        """Execute hybrid search using the available repository or asyncpg connection."""
        if self._repository is not None and hasattr(self._repository, "search_memories_hybrid"):
            return await self._repository.search_memories_hybrid(
                user_id=user_id,
                query_text=query_text,
                query_embedding=query_embedding,
                limit=limit,
                min_similarity=min_similarity,
            )

        if self._db_pool is not None:
            async with self._db_pool.acquire() as conn:
                await conn.execute(f"SET request.jwt.claim.sub = '{user_id}'")
                embedding_str = f"[{','.join(str(x) for x in query_embedding)}]" if query_embedding else None
                rows = await conn.fetch(
                    """
                    SELECT id, content, memory_type, category, importance, confidence, confirmation_status, score
                    FROM public.search_memories_hybrid_rpc(
                        p_query_text => $1,
                        p_query_embedding => $2::vector,
                        p_limit => $3,
                        p_min_similarity => $4
                    )
                    """,
                    query_text,
                    embedding_str,
                    limit,
                    min_similarity,
                )
                return [
                    MemorySearchResult(
                        id=r["id"],
                        content=r["content"],
                        memory_type=r["memory_type"],
                        category=r["category"],
                        importance=r["importance"],
                        confidence=r["confidence"],
                        confirmation_status=r["confirmation_status"],
                        score=float(r["score"]),
                    )
                    for r in rows
                ]

        return []

