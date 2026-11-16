"""Journal consent token verification service for AUREN.

Ensures that access to private journal entries is strictly gated by an explicit,
cryptographically signed HMAC token issued by the trusted backend.

Enforces:
1. Cryptographic signature integrity via HMAC-SHA256 (constant-time comparison).
2. Binding to exact user_id, conversation_id, idempotency_key, scope, date_range, and nonce.
3. Strict scope validation against permitted whitelist.
4. Expiration enforcement and maximum 15-minute lifetime limit.
5. Replay protection via atomic PostgreSQL nonce consumption.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Optional, Set
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ALLOWED_JOURNAL_SCOPES: Set[str] = {
    "journal.read",
    "journal.read_write",
    "journal.summarize",
}

MAX_TOKEN_LIFETIME_SECONDS = 900  # 15 minutes


class ConsentVerificationError(Exception):
    """Base exception for journal consent verification failures."""

    pass


class InvalidSignatureError(ConsentVerificationError):
    """Raised when HMAC signature does not match or has been tampered with."""

    pass


class ExpiredConsentTokenError(ConsentVerificationError):
    """Raised when the consent token has passed its expiration time."""

    pass


class ExcessiveLifetimeError(ConsentVerificationError):
    """Raised when a consent token has an expiration exceeding the maximum allowed window."""

    pass


class ConsentUserMismatchError(ConsentVerificationError):
    """Raised when the consent token belongs to a different user."""

    pass


class ConsentConversationMismatchError(ConsentVerificationError):
    """Raised when the consent token is presented for a different conversation."""

    pass


class ConsentIdempotencyMismatchError(ConsentVerificationError):
    """Raised when the consent token is presented for a different idempotency key."""

    pass


class InvalidConsentScopeError(ConsentVerificationError):
    """Raised when the consent token has an unrecognized or unauthorized scope."""

    pass


class ReplayedConsentTokenError(ConsentVerificationError):
    """Raised when a consent nonce has already been consumed in the database."""

    pass


class JournalConsentPayload(BaseModel):
    """Canonical parameters bound to a journal consent authorization."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    conversation_id: UUID
    idempotency_key: str
    scope: str
    date_range: str
    nonce: UUID
    expires_at: datetime


class JournalConsentToken(BaseModel):
    """Signed journal consent token containing payload and HMAC signature."""

    model_config = ConfigDict(frozen=True)

    payload: JournalConsentPayload
    signature: str


def compute_consent_signature(payload: JournalConsentPayload, secret: str) -> str:
    """Computes deterministic HMAC-SHA256 signature over the canonical representation of the payload."""
    canonical_string = (
        f"user:{payload.user_id}|"
        f"conv:{payload.conversation_id}|"
        f"idemp:{payload.idempotency_key.strip()}|"
        f"scope:{payload.scope.strip()}|"
        f"range:{payload.date_range.strip()}|"
        f"nonce:{payload.nonce}|"
        f"exp:{int(payload.expires_at.timestamp())}"
    )
    return hmac.new(
        secret.encode("utf-8"),
        canonical_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_journal_consent_token(
    user_id: UUID,
    conversation_id: UUID,
    idempotency_key: str,
    scope: str,
    date_range: str,
    nonce: UUID,
    expires_at: datetime,
    secret: str,
) -> JournalConsentToken:
    """Issues a cryptographically signed journal consent token."""
    if scope not in ALLOWED_JOURNAL_SCOPES:
        raise InvalidConsentScopeError(
            f"Scope '{scope}' is not in permitted scopes: {ALLOWED_JOURNAL_SCOPES}"
        )
    payload = JournalConsentPayload(
        user_id=user_id,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        scope=scope,
        date_range=date_range,
        nonce=nonce,
        expires_at=expires_at,
    )
    sig = compute_consent_signature(payload, secret)
    return JournalConsentToken(payload=payload, signature=sig)


def verify_journal_consent_token(
    token: JournalConsentToken,
    secret: str,
    expected_user_id: UUID,
    expected_conversation_id: UUID,
    expected_idempotency_key: str,
    now: Optional[datetime] = None,
) -> bool:
    """Verifies HMAC signature, bound request fields, expiration, and lifetime.

    Does NOT consume the nonce in the database. Returns True if valid, or raises
    a specific ConsentVerificationError subclass on failure.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 1. Verify HMAC signature using constant-time comparison
    expected_sig = compute_consent_signature(token.payload, secret)
    if not hmac.compare_digest(expected_sig, token.signature):
        raise InvalidSignatureError("Consent token signature is invalid or tampered.")

    # 2. Scope validation against permitted whitelist
    if token.payload.scope not in ALLOWED_JOURNAL_SCOPES:
        raise InvalidConsentScopeError(f"Invalid consent scope: {token.payload.scope}")

    # 3. User binding validation
    if token.payload.user_id != expected_user_id:
        raise ConsentUserMismatchError(
            f"Consent user_id {token.payload.user_id} does not match expected {expected_user_id}"
        )

    # 4. Conversation binding validation
    if token.payload.conversation_id != expected_conversation_id:
        raise ConsentConversationMismatchError(
            f"Consent conversation_id {token.payload.conversation_id} does not match expected {expected_conversation_id}"
        )

    # 5. Idempotency key binding validation
    if token.payload.idempotency_key.strip() != expected_idempotency_key.strip():
        raise ConsentIdempotencyMismatchError("Consent idempotency_key mismatch.")

    # 6. Expiration check
    if now > token.payload.expires_at:
        raise ExpiredConsentTokenError("Consent token has expired.")

    # 7. Maximum lifetime check (15 minutes from now)
    if token.payload.expires_at > now + timedelta(seconds=MAX_TOKEN_LIFETIME_SECONDS):
        raise ExcessiveLifetimeError(
            "Consent token lifetime exceeds maximum permitted window of 15 minutes."
        )

    return True


async def verify_and_consume_journal_consent(
    token: JournalConsentToken,
    secret: str,
    expected_user_id: UUID,
    expected_conversation_id: UUID,
    expected_idempotency_key: str,
    db_conn,
    now: Optional[datetime] = None,
) -> bool:
    """Verifies HMAC signature and bounds in Python, then atomically consumes the nonce in PostgreSQL.

    If verification fails, journal extraction MUST remain disabled.
    """
    # Verify cryptographic signature and bound fields first
    verify_journal_consent_token(
        token=token,
        secret=secret,
        expected_user_id=expected_user_id,
        expected_conversation_id=expected_conversation_id,
        expected_idempotency_key=expected_idempotency_key,
        now=now,
    )

    # Atomically record nonce consumption in PostgreSQL ledger
    try:
        consumed = await db_conn.fetchval(
            """
            SELECT public.consume_journal_consent_rpc(
                p_nonce => $1,
                p_conversation_id => $2,
                p_idempotency_key => $3,
                p_scope => $4,
                p_expires_at => $5
            )
            """,
            token.payload.nonce,
            token.payload.conversation_id,
            token.payload.idempotency_key,
            token.payload.scope,
            token.payload.expires_at,
        )
        return bool(consumed)
    except Exception as exc:
        err_msg = str(exc)
        if "already been consumed" in err_msg or "23505" in err_msg:
            raise ReplayedConsentTokenError("Consent token has already been consumed (replay rejected).") from exc
        raise

