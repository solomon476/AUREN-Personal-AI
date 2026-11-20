"""Journal record cryptographic integrity signing and verification service.

Uses RFC 8785 JSON Canonicalization Scheme (JCS) and HMAC-SHA256 to sign
and verify journal records against out-of-band tampering or accidental modification.
"""

from datetime import date
import hashlib
import hmac
import logging
from typing import List, Optional
from uuid import UUID

from app.core.config import settings
from app.services.journal.rfc8785 import canonicalize

logger = logging.getLogger(__name__)


def build_canonical_journal_dict(
    entry_id: UUID,
    user_id: UUID,
    title: Optional[str],
    content: str,
    mood: Optional[str],
    tags: List[str],
    entry_date: date,
    is_private: bool = True,
) -> dict:
    """Builds a normalized dictionary representing the core data fields of a journal entry.

    Fields are normalized to deterministic scalar types before RFC 8785 canonical serialization.
    """
    clean_tags = sorted(list(set(tags or [])))
    return {
        "content": str(content),
        "entry_date": entry_date.isoformat() if isinstance(entry_date, date) else str(entry_date)[:10],
        "id": str(entry_id),
        "is_private": bool(is_private),
        "mood": str(mood or ""),
        "tags": clean_tags,
        "title": str(title or ""),
        "user_id": str(user_id),
    }


def compute_journal_signature(
    entry_id: UUID,
    user_id: UUID,
    title: Optional[str],
    content: str,
    mood: Optional[str],
    tags: List[str],
    entry_date: date,
    is_private: bool = True,
    secret: Optional[str] = None,
) -> str:
    """Computes an HMAC-SHA256 signature for a journal entry using RFC 8785 canonical JSON."""
    raw_secret = secret
    if not raw_secret:
        try:
            raw_secret = settings.get_journal_hmac_secret()
        except Exception as exc:
            logger.warning("Could not obtain JOURNAL_HMAC_SECRET: %s", exc)
            raw_secret = "default-fallback-insecure-journal-secret-for-tests-only"

    canonical_payload = build_canonical_journal_dict(
        entry_id=entry_id,
        user_id=user_id,
        title=title,
        content=content,
        mood=mood,
        tags=tags,
        entry_date=entry_date,
        is_private=is_private,
    )
    canonical_bytes = canonicalize(canonical_payload)
    return hmac.new(
        key=raw_secret.encode("utf-8"),
        msg=canonical_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_journal_signature(
    entry_id: UUID,
    user_id: UUID,
    title: Optional[str],
    content: str,
    mood: Optional[str],
    tags: List[str],
    entry_date: date,
    signature: Optional[str],
    is_private: bool = True,
    secret: Optional[str] = None,
) -> bool:
    """Verifies that the provided signature matches the RFC 8785 HMAC-SHA256 hash of the entry."""
    if not signature or not isinstance(signature, str):
        return False

    try:
        expected_sig = compute_journal_signature(
            entry_id=entry_id,
            user_id=user_id,
            title=title,
            content=content,
            mood=mood,
            tags=tags,
            entry_date=entry_date,
            is_private=is_private,
            secret=secret,
        )
        return hmac.compare_digest(expected_sig, signature.strip())
    except Exception as exc:
        logger.warning("Error verifying journal signature: %s", exc)
        return False
