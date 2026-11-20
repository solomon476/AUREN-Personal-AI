"""Unit tests verifying that the background memory worker respects user extraction preferences."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from app.services.memory.models import ExtractedMemoryItem
from app.services.memory.worker import MemoryExtractionWorker


@pytest.fixture
def mock_worker():
    llm_provider = MagicMock()
    embedding_provider = MagicMock()
    embedding_provider.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
    worker = MemoryExtractionWorker(
        db_pool=MagicMock(),
        worker_id="test_worker_01",
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
    )
    return worker


@pytest.mark.asyncio
async def test_worker_skips_extraction_when_auto_extraction_disabled(mock_worker):
    mock_conn = MagicMock()
    job_id = uuid4()
    claim_token = uuid4()
    user_id = uuid4()

    mock_worker.fetch_source_turn = AsyncMock(return_value={
        "user_id": user_id,
        "user_message_content": "I like dark mode.",
        "assistant_content": "Noted!",
    })
    # User has disabled auto extraction
    mock_worker.get_user_preferences = AsyncMock(return_value={
        "memory_auto_extraction": False,
    })
    mock_worker.complete_job = AsyncMock()
    mock_worker.extract_memories = AsyncMock()

    job = {"id": job_id, "claim_token": claim_token}
    result = await mock_worker.process_job(mock_conn, job)

    assert result is True
    # Verify extract_memories was NEVER called
    mock_worker.extract_memories.assert_not_called()
    mock_worker.complete_job.assert_awaited_once_with(mock_conn, job_id, claim_token)


@pytest.mark.asyncio
async def test_worker_filters_out_memories_below_confidence_threshold(mock_worker):
    mock_conn = MagicMock()
    job_id = uuid4()
    claim_token = uuid4()
    user_id = uuid4()

    mock_worker.fetch_source_turn = AsyncMock(return_value={
        "user_id": user_id,
        "user_message_content": "I am working on Project Alpha.",
        "assistant_content": "Great!",
    })
    # User threshold is 0.85
    mock_worker.get_user_preferences = AsyncMock(return_value={
        "memory_auto_extraction": True,
        "memory_min_confidence": 0.85,
    })
    # LLM returns one low confidence (0.70) and one high confidence (0.90) memory
    mock_worker.extract_memories = AsyncMock(return_value=[
        ExtractedMemoryItem(content="Low confidence fact", memory_type="fact", category="general", confidence=0.70),
        ExtractedMemoryItem(content="High confidence fact", memory_type="fact", category="general", confidence=0.90),
    ])
    mock_worker.ingest_memory = AsyncMock()
    mock_worker.complete_job = AsyncMock()

    job = {"id": job_id, "claim_token": claim_token}
    result = await mock_worker.process_job(mock_conn, job)

    assert result is True
    # Only the 0.90 item should be ingested!
    assert mock_worker.ingest_memory.await_count == 1
    ingested_item = mock_worker.ingest_memory.call_args[0][3]
    assert ingested_item.content == "High confidence fact"
    assert ingested_item.confidence == 0.90
    mock_worker.complete_job.assert_awaited_once_with(mock_conn, job_id, claim_token)


@pytest.mark.asyncio
async def test_worker_completes_cleanly_when_all_memories_below_threshold(mock_worker):
    mock_conn = MagicMock()
    job_id = uuid4()
    claim_token = uuid4()
    user_id = uuid4()

    mock_worker.fetch_source_turn = AsyncMock(return_value={
        "user_id": user_id,
        "user_message_content": "Maybe I will travel somewhere someday.",
        "assistant_content": "Nice!",
    })
    mock_worker.get_user_preferences = AsyncMock(return_value={
        "memory_auto_extraction": True,
        "memory_min_confidence": 0.80,
    })
    mock_worker.extract_memories = AsyncMock(return_value=[
        ExtractedMemoryItem(content="Weak inference", memory_type="fact", category="general", confidence=0.65),
    ])
    mock_worker.ingest_memory = AsyncMock()
    mock_worker.complete_job = AsyncMock()

    job = {"id": job_id, "claim_token": claim_token}
    result = await mock_worker.process_job(mock_conn, job)

    assert result is True
    # Zero items ingested
    mock_worker.ingest_memory.assert_not_called()
    mock_worker.complete_job.assert_awaited_once_with(mock_conn, job_id, claim_token)
