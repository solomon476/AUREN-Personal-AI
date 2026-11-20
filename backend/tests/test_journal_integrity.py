"""Comprehensive unit tests for AUREN Journal RFC 8785 HMAC integrity architecture."""

from datetime import date
from pathlib import Path
import sqlite3
import tempfile
from uuid import UUID, uuid4
import pytest

from app.models.journal import JournalEntryCreate, JournalEntryUpdate
from app.services.journal.integrity import (
    build_canonical_journal_dict,
    compute_journal_signature,
    verify_journal_signature,
)
from app.services.journal.sqlite_repository import SQLiteJournalRepository


@pytest.fixture
def test_secret():
    return "test-cryptographic-journal-secret-key-32chars"


@pytest.fixture
def temp_journal_repo(tmp_path: Path):
    db_path = tmp_path / "test_integrity_journal.db"
    return SQLiteJournalRepository(db_path=db_path)


def test_integrity_signature_computation_and_verification(test_secret):
    entry_id = uuid4()
    user_id = uuid4()
    title = "My Evening Reflection"
    content = "Today I made solid progress on architecture hardening."
    mood = "reflective"
    tags = ["architecture", "crypto"]
    entry_date = date(2026, 11, 20)

    sig = compute_journal_signature(
        entry_id=entry_id,
        user_id=user_id,
        title=title,
        content=content,
        mood=mood,
        tags=tags,
        entry_date=entry_date,
        is_private=True,
        secret=test_secret,
    )
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA-256 hex string

    # Verify matching payload passes
    assert verify_journal_signature(
        entry_id=entry_id,
        user_id=user_id,
        title=title,
        content=content,
        mood=mood,
        tags=tags,
        entry_date=entry_date,
        signature=sig,
        is_private=True,
        secret=test_secret,
    ) is True


def test_tampered_journal_attributes_detected(test_secret):
    entry_id = uuid4()
    user_id = uuid4()
    title = "Original Title"
    content = "Original Content"
    mood = "calm"
    tags = ["tag1"]
    entry_date = date(2026, 11, 20)

    sig = compute_journal_signature(
        entry_id=entry_id,
        user_id=user_id,
        title=title,
        content=content,
        mood=mood,
        tags=tags,
        entry_date=entry_date,
        is_private=True,
        secret=test_secret,
    )

    # Tamper content
    assert verify_journal_signature(
        entry_id=entry_id,
        user_id=user_id,
        title=title,
        content="Tampered Content",
        mood=mood,
        tags=tags,
        entry_date=entry_date,
        signature=sig,
        is_private=True,
        secret=test_secret,
    ) is False

    # Tamper title
    assert verify_journal_signature(
        entry_id=entry_id,
        user_id=user_id,
        title="Tampered Title",
        content=content,
        mood=mood,
        tags=tags,
        entry_date=entry_date,
        signature=sig,
        is_private=True,
        secret=test_secret,
    ) is False

    # Tamper tags
    assert verify_journal_signature(
        entry_id=entry_id,
        user_id=user_id,
        title=title,
        content=content,
        mood=mood,
        tags=["tag1", "tampered_tag"],
        entry_date=entry_date,
        signature=sig,
        is_private=True,
        secret=test_secret,
    ) is False

    # Tamper date
    assert verify_journal_signature(
        entry_id=entry_id,
        user_id=user_id,
        title=title,
        content=content,
        mood=mood,
        tags=tags,
        entry_date=date(2026, 11, 21),
        signature=sig,
        is_private=True,
        secret=test_secret,
    ) is False


@pytest.mark.asyncio
async def test_sqlite_repository_integrity_lifecycle(temp_journal_repo):
    user_id = uuid4()

    # 1. Create entry
    create_payload = JournalEntryCreate(
        title="Architecture Log",
        content="Testing SQLite repository integrity signing.",
        mood="focused",
        tags=["audit", "verification"],
        is_private=True,
        entry_date=date(2026, 11, 20),
    )
    entry = await temp_journal_repo.create_entry(user_id=user_id, payload=create_payload)

    assert entry.integrity_signature is not None
    assert entry.integrity_verified is True

    # 2. Retrieve entry
    retrieved = await temp_journal_repo.get_entry(user_id=user_id, entry_id=entry.id)
    assert retrieved is not None
    assert retrieved.integrity_verified is True
    assert retrieved.integrity_signature == entry.integrity_signature

    # 3. Legitimate update re-signs correctly
    update_payload = JournalEntryUpdate(
        content="Updated reflection content with legitimate API caller.",
        mood="energized",
    )
    updated = await temp_journal_repo.update_entry(
        user_id=user_id,
        entry_id=entry.id,
        payload=update_payload,
    )
    assert updated is not None
    assert updated.content == "Updated reflection content with legitimate API caller."
    assert updated.integrity_verified is True
    assert updated.integrity_signature != entry.integrity_signature

    # 4. Out-of-band database tampering is detected
    with sqlite3.connect(str(temp_journal_repo.db_path)) as conn:
        conn.execute(
            "UPDATE journal_entries SET content = 'MALICIOUS_TAMPERED_INJECTION' WHERE id = ?",
            (str(entry.id),),
        )
        conn.commit()

    tampered_entry = await temp_journal_repo.get_entry(user_id=user_id, entry_id=entry.id)
    assert tampered_entry is not None
    assert tampered_entry.content == "MALICIOUS_TAMPERED_INJECTION"
    # Verification MUST fail on tampered record!
    assert tampered_entry.integrity_verified is False


@pytest.mark.asyncio
async def test_legacy_journal_entry_without_signature(temp_journal_repo):
    user_id = uuid4()
    entry_id = str(uuid4())

    # Insert legacy row without signature
    with sqlite3.connect(str(temp_journal_repo.db_path)) as conn:
        conn.execute(
            """
            INSERT INTO journal_entries (
                id, user_id, title, content, mood, tags, is_private, entry_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                str(user_id),
                "Legacy Entry",
                "Old record before integrity signing was enabled.",
                "neutral",
                "[]",
                1,
                "2026-11-01",
                "2026-11-01T10:00:00",
                "2026-11-01T10:00:00",
            ),
        )
        conn.commit()

    legacy = await temp_journal_repo.get_entry(user_id=user_id, entry_id=UUID(entry_id))
    assert legacy is not None
    assert legacy.integrity_signature is None
    assert legacy.integrity_verified is None


def test_verify_signature_resilient_to_malformed_inputs():
    # Empty signature or non-string signature
    assert verify_journal_signature(uuid4(), uuid4(), "Title", "Content", "mood", [], date.today(), None) is False
    assert verify_journal_signature(uuid4(), uuid4(), "Title", "Content", "mood", [], date.today(), "") is False
    # Malformed secret exception handled gracefully
    assert verify_journal_signature(uuid4(), uuid4(), "Title", "Content", "mood", [], date.today(), "abc", secret="") is not None
