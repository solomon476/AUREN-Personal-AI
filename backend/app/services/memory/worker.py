"""Asynchronous background worker service for extracting persistent memories from completed chat turns."""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.services.embeddings.base import BaseEmbeddingProvider
from app.services.llm.base import BaseLLMProvider, ChatMessage
from app.services.memory.models import ExtractedMemoryItem
from app.services.memory.queue_sanitizer import sanitize_extraction_error

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are AUREN's durable memory extraction engine.
Analyze the user and assistant dialogue exchange and extract salient, long-term personal facts, user preferences, projects, and goals.

Rules:
1. ONLY extract information that has enduring value across future conversations.
2. DO NOT extract fleeting transactional chatter, greetings, or temporary pleasantries.
3. NEVER manufacture certainty. Inferred dialogue MUST be represented as inferences.
4. Classify each memory into:
   - memory_type: 'fact', 'preference', 'goal', 'project', 'context', or 'observation'
   - category: 'personal', 'work', 'technical', 'health_lifestyle', 'financial', or 'general'
   - importance: integer 1 to 5 (1 = minor detail, 5 = core life/identity facet)
   - confidence: float 0.0 to 1.0 (typical inference is 0.7 to 0.85)

Output format:
Respond ONLY with a JSON array of objects, each containing:
[
  {
    "content": "User prefers concise answers with bullet points",
    "memory_type": "preference",
    "category": "technical",
    "importance": 4,
    "confidence": 0.85
  }
]
If nothing of durable value is present, return []."""


class MemoryExtractionWorker:
    """Worker process claiming and processing memory extraction jobs with claim-token fencing."""

    def __init__(
        self,
        worker_id: str,
        db_pool,
        llm_provider: BaseLLMProvider,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        batch_size: int = 5,
        lease_seconds: int = 300,
    ):
        self.worker_id = worker_id
        self.db_pool = db_pool
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider
        self.batch_size = batch_size
        self.lease_seconds = lease_seconds

    async def claim_jobs(self, conn, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Claims a batch of pending or expired jobs using atomic SKIP LOCKED RPC."""
        actual_limit = limit if limit is not None else self.batch_size
        rows = await conn.fetch(
            """
            SELECT id, user_id, conversation_id, source_message_id, claim_token, attempts, max_attempts
            FROM public.claim_memory_extraction_jobs_rpc(
                p_worker_id => $1,
                p_batch_size => $2,
                p_lease_seconds => $3
            )
            """,
            self.worker_id,
            actual_limit,
            self.lease_seconds,
        )
        return [dict(r) for r in rows]

    async def fetch_source_turn(self, conn, job_id: UUID, claim_token: UUID) -> Optional[Dict[str, Any]]:
        """Fetches the source message pair strictly enforcing claim token, lease, and quarantine checks."""
        try:
            row = await conn.fetchrow(
                """
                SELECT job_id, user_id, conversation_id, source_message_id, assistant_content, assistant_role, user_message_content
                FROM public.fetch_extraction_source_message_rpc(
                    p_job_id => $1,
                    p_worker_id => $2,
                    p_claim_token => $3
                )
                """,
                job_id,
                self.worker_id,
                claim_token,
            )
            return dict(row) if row else None
        except Exception as exc:
            logger.info("Source fetch rejected or quarantined for job %s: %s", job_id, exc)
            return None

    async def extract_memories(self, user_text: str, assistant_text: str) -> List[ExtractedMemoryItem]:
        """Invokes the LLM provider to extract structured memories from the dialogue turn."""
        messages = [
            ChatMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=f"User Statement:\n{user_text}\n\nAssistant Response:\n{assistant_text}",
            ),
        ]
        try:
            response = await self.llm_provider.generate_response(messages, temperature=0.1)
            raw_text = response.content.strip()

            # Extract JSON array
            match = re.search(r"\[\s*\{.*\}\s*\]", raw_text, re.DOTALL)
            if not match:
                if "[]" in raw_text:
                    return []
                return []

            data = json.loads(match.group(0))
            items: List[ExtractedMemoryItem] = []
            for d in data:
                try:
                    items.append(
                        ExtractedMemoryItem(
                            content=d["content"],
                            memory_type=d.get("memory_type", "fact"),
                            category=d.get("category", "general"),
                            importance=int(d.get("importance", 3)),
                            confidence=float(d.get("confidence", 0.7)),
                        )
                    )
                except Exception as parse_err:
                    logger.warning("Failed parsing individual extracted item %s: %s", d, parse_err)
            return items
        except Exception as exc:
            logger.warning("LLM memory extraction failed: %s", exc)
            raise

    async def ingest_memory(
        self,
        conn,
        job_id: UUID,
        claim_token: UUID,
        item: ExtractedMemoryItem,
        embedding: Optional[List[float]] = None,
    ) -> UUID:
        """Persists extracted memory via insert_extracted_memory_rpc, enforcing epistemic constraints."""
        embedding_str = f"[{','.join(str(x) for x in embedding)}]" if embedding else None
        if embedding is not None and self.embedding_provider is not None:
            model_id = self.embedding_provider.get_model_id()
            provider_name = getattr(self.embedding_provider, "get_provider_name", lambda: "gemini")()
            version = getattr(self.embedding_provider, "get_version", lambda: "v1")()
            dimension = getattr(self.embedding_provider, "get_dimension", lambda: 768)()
        else:
            model_id = "gemini-embedding-2"
            provider_name = "gemini"
            version = "v1"
            dimension = 768

        return await conn.fetchval(
            """
            SELECT public.insert_extracted_memory_rpc(
                p_job_id => $1,
                p_worker_id => $2,
                p_claim_token => $3,
                p_content => $4,
                p_memory_type => $5,
                p_category => $6,
                p_importance => $7,
                p_confidence => $8,
                p_metadata => $9::jsonb,
                p_embedding_768 => $10::vector,
                p_model => $11,
                p_provider => $12,
                p_version => $13,
                p_dimension => $14
            )
            """,
            job_id,
            self.worker_id,
            claim_token,
            item.content,
            item.memory_type,
            item.category,
            item.importance,
            item.confidence,
            json.dumps(item.metadata),
            embedding_str,
            model_id,
            provider_name,
            version,
            dimension,
        )

    async def complete_job(self, conn, job_id: UUID, claim_token: UUID) -> bool:
        """Transitions job to completed and rotates active claim token."""
        return await conn.fetchval(
            "SELECT public.complete_memory_extraction_job_rpc($1, $2, $3)",
            job_id,
            self.worker_id,
            claim_token,
        )

    async def fail_job(self, conn, job_id: UUID, claim_token: UUID, error: Exception, retry: bool = True) -> bool:
        """Records sanitized failure and reschedules or dead-letters the job."""
        sanitized = sanitize_extraction_error(error)
        return await conn.fetchval(
            "SELECT public.fail_memory_extraction_job_rpc($1, $2, $3, $4, $5)",
            job_id,
            self.worker_id,
            claim_token,
            sanitized,
            retry,
        )

    async def get_user_preferences(self, conn, user_id: UUID) -> Dict[str, Any]:
        """Fetches user preferences to enforce extraction toggles and confidence thresholds."""
        try:
            raw = await conn.fetchval(
                "SELECT public.get_user_extraction_preferences_rpc($1, $2)",
                user_id,
                self.worker_id,
            )
            if raw:
                if isinstance(raw, str):
                    return json.loads(raw)
                return dict(raw)
        except Exception:
            pass
        try:
            raw = await conn.fetchval(
                "SELECT preferences FROM public.profiles WHERE id = $1",
                user_id,
            )
            if raw:
                if isinstance(raw, str):
                    return json.loads(raw)
                return dict(raw)
        except Exception:
            pass
        return {}

    async def process_job(self, conn, job: Dict[str, Any]) -> bool:
        """Processes a single extraction job end-to-end with full error sanitization and lease checks."""
        job_id = job["id"]
        claim_token = job["claim_token"]

        try:
            # 1. Fetch source message pair (fail-closed if quarantined or invalid)
            source = await self.fetch_source_turn(conn, job_id, claim_token)
            if not source:
                # Turn was quarantined or invalid; RPC already handled dead-lettering
                return False

            # Check user preferences for extraction policies
            user_prefs = await self.get_user_preferences(conn, source["user_id"])
            if user_prefs.get("memory_auto_extraction") is False:
                logger.info(
                    "Memory auto-extraction is disabled for user %s; skipping extraction for job %s",
                    source["user_id"],
                    job_id,
                )
                await self.complete_job(conn, job_id, claim_token)
                return True

            min_confidence = float(user_prefs.get("memory_min_confidence", 0.7))

            # 2. Extract durable memories
            extracted_items = await self.extract_memories(
                user_text=source["user_message_content"],
                assistant_text=source["assistant_content"],
            )

            # Filter items respecting user's confidence threshold
            qualified_items = [
                item for item in extracted_items
                if item.confidence >= min_confidence
            ]

            if not qualified_items:
                logger.info(
                    "No extracted memories met the user confidence threshold (%f) for job %s",
                    min_confidence,
                    job_id,
                )
                await self.complete_job(conn, job_id, claim_token)
                return True

            # 3. Generate embeddings if embedding provider configured
            embeddings: List[Optional[List[float]]] = [None] * len(qualified_items)
            if qualified_items and self.embedding_provider is not None:
                texts = [item.content for item in qualified_items]
                embeddings = await self.embedding_provider.embed_batch(texts)

            # 4. Ingest each extracted memory with its vector embedding
            for item, emb in zip(qualified_items, embeddings):
                await self.ingest_memory(conn, job_id, claim_token, item, embedding=emb)

            # 5. Atomically complete the job with terminal lease cleanup
            await self.complete_job(conn, job_id, claim_token)
            return True

        except Exception as exc:
            logger.warning("Error processing extraction job %s: %s", job_id, exc)
            try:
                await self.fail_job(conn, job_id, claim_token, exc, retry=True)
            except Exception as fail_err:
                logger.error("Failed to record failure for job %s: %s", job_id, fail_err)
            return False

    async def run_once(self) -> int:
        """Executes one polling and execution cycle. Returns number of jobs claimed."""
        async with self.db_pool.acquire() as conn:
            jobs = await self.claim_jobs(conn)
            if not jobs:
                return 0

            for job in jobs:
                await self.process_job(conn, job)

            return len(jobs)

