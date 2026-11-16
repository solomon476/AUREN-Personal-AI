"""Tests for RFC 8785 (JCS) Canonical JSON implementation and Journal Consent verification."""

from datetime import datetime, timedelta, timezone
import json
import math
import struct
from uuid import UUID, uuid4
import pytest

from app.services.journal.rfc8785 import (
    canonicalize,
    canonicalize_to_str,
    escape_string,
    float_to_ecma,
)
from app.services.journal.consent import (
    ALLOWED_JOURNAL_SCOPES,
    ConsentConversationMismatchError,
    ConsentIdempotencyMismatchError,
    ConsentUserMismatchError,
    DateRangeMismatchError,
    ExcessiveLifetimeError,
    ExpiredConsentTokenError,
    InvalidConsentScopeError,
    InvalidSignatureError,
    JournalConsentPayload,
    JournalConsentToken,
    compute_consent_signature,
    create_journal_consent_token,
    serialize_canonical_payload,
    verify_journal_consent_token,
)


def test_rfc8785_section_3_2_4_normative_hex_vector():
    """Validates the exact normative sample from RFC 8785 Sections 3.2.2, 3.2.3, and 3.2.4.

    The expected byte output must match the published RFC hex string byte-for-byte.
    """
    # Sample string containing: \u20ac, $, U+000F, \n, A', B, ", \\, \\, ", /
    s = "\u20ac$\x0f\nA'B\"" + chr(92) + chr(92) + "\"/"
    obj = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 0.000000000000000000000000001],
        "string": s,
        "literals": [None, True, False],
    }

    res_bytes = canonicalize(obj)

    expected_hex = (
        "7b 22 6c 69 74 65 72 61 6c 73 22 3a 5b 6e 75 6c 6c 2c 74 72 "
        "75 65 2c 66 61 6c 73 65 5d 2c 22 6e 75 6d 62 65 72 73 22 3a "
        "5b 33 33 33 33 33 33 33 33 33 2e 33 33 33 33 33 33 33 2c 31 "
        "65 2b 33 30 2c 34 2e 35 2c 30 2e 30 30 32 2c 31 65 2d 32 37 "
        "5d 2c 22 73 74 72 69 6e 67 22 3a 22 e2 82 ac 24 5c 75 30 30 "
        "30 66 5c 6e 41 27 42 5c 22 5c 5c 5c 5c 5c 22 2f 22 7d"
    )
    expected_bytes = bytes.fromhex(expected_hex.replace(" ", ""))

    assert res_bytes == expected_bytes
    assert res_bytes.decode("utf-8") == expected_bytes.decode("utf-8")


def test_rfc8785_section_3_2_3_property_sorting_vector():
    """Validates property sorting according to RFC 8785 Section 3.2.3 test data.

    Demonstrates that UTF-16 code-unit sorting places Emoji (surrogate pair 0xD83D, 0xDE00)
    BEFORE Hebrew Letter Dalet With Dagesh (U+FB33), whereas Unicode code-point sorting
    would incorrectly place Hebrew Letter before Emoji.
    """
    json_text = r"""{
      "\u20ac": "Euro Sign",
      "\r": "Carriage Return",
      "\ufb33": "Hebrew Letter Dalet With Dagesh",
      "1": "One",
      "\ud83d\ude00": "Emoji: Grinning Face",
      "\u0080": "Control",
      "\u00f6": "Latin Small Letter O With Diaeresis"
    }"""
    test_obj = json.loads(json_text)
    sorted_keys = sorted(test_obj.keys(), key=lambda k: k.encode("utf-16-be"))
    actual_order = [test_obj[k] for k in sorted_keys]

    expected_order = [
        "Carriage Return",
        "One",
        "Control",
        "Latin Small Letter O With Diaeresis",
        "Euro Sign",
        "Emoji: Grinning Face",
        "Hebrew Letter Dalet With Dagesh",
    ]
    assert actual_order == expected_order

    # Verify that canonicalize serializes keys in this exact order
    serialized = canonicalize_to_str(test_obj)
    order_in_serialized = [
        desc for desc in expected_order if f'"{desc}"' in serialized
    ]
    # Check that positions appear in increasing order
    positions = [serialized.index(f'"{desc}"') for desc in expected_order]
    assert positions == sorted(positions)


def test_utf16_vs_unicode_codepoint_property_ordering_divergence():
    """Explicitly tests property names where UTF-16 code-unit ordering differs from Python code-point ordering."""
    key_bmp = "\uFFFF"          # Code point 0xFFFF (UTF-16: 0xFFFF)
    key_supp = "\U00010000"      # Code point 0x10000 (UTF-16: 0xD800, 0xDC00)

    # In Python default code point comparison:
    assert key_bmp < key_supp, "In code points, 0xFFFF is strictly less than 0x10000"

    # In RFC 8785 UTF-16 code unit comparison:
    assert key_supp.encode("utf-16-be") < key_bmp.encode("utf-16-be"), (
        "In UTF-16 code units, surrogate 0xD800 is strictly less than BMP 0xFFFF"
    )

    obj = {key_bmp: "bmp", key_supp: "supp"}
    canonical = canonicalize_to_str(obj)

    # key_supp MUST precede key_bmp in the canonical output
    idx_supp = canonical.index('"supp"')
    idx_bmp = canonical.index('"bmp"')
    assert idx_supp < idx_bmp, "Supplementary plane key MUST precede BMP key \uFFFF under RFC 8785"


def test_rfc8785_appendix_b_numbers():
    """Validates all 24 IEEE 754 sample values from RFC 8785 Appendix B, Table 1."""
    samples = [
        ("0000000000000000", "0"),
        ("8000000000000000", "0"),
        ("0000000000000001", "5e-324"),
        ("8000000000000001", "-5e-324"),
        ("7fefffffffffffff", "1.7976931348623157e+308"),
        ("ffefffffffffffff", "-1.7976931348623157e+308"),
        ("4340000000000000", "9007199254740992"),
        ("c340000000000000", "-9007199254740992"),
        ("4430000000000000", "295147905179352830000"),
        ("44b52d02c7e14af5", "9.999999999999997e+22"),
        ("44b52d02c7e14af6", "1e+23"),
        ("44b52d02c7e14af7", "1.0000000000000001e+23"),
        ("444b1ae4d6e2ef4e", "999999999999999700000"),
        ("444b1ae4d6e2ef4f", "999999999999999900000"),
        ("444b1ae4d6e2ef50", "1e+21"),
        ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
        ("3eb0c6f7a0b5ed8d", "0.000001"),
        ("41b3de4355555553", "333333333.3333332"),
        ("41b3de4355555554", "333333333.33333325"),
        ("41b3de4355555555", "333333333.3333333"),
        ("41b3de4355555556", "333333333.3333334"),
        ("41b3de4355555557", "333333333.33333343"),
        ("becbf647612f3696", "-0.0000033333333333333333"),
        ("43143ff3c1cb0959", "1424953923781206.2"),
    ]
    for hex_repr, expected in samples:
        val = struct.unpack(">d", bytes.fromhex(hex_repr))[0]
        actual = float_to_ecma(val)
        assert actual == expected, f"Failed for {hex_repr}: got {actual!r}, expected {expected!r}"


def test_string_escaping_control_characters_and_solidus():
    """Validates minimal escaping rules for strings and control characters."""
    # Quotation mark and backslash must be escaped
    assert escape_string('"') == r'"\""'
    assert escape_string("\\") == r'"\\"'

    # Predefined control chars
    assert escape_string("\b") == r'"\b"'
    assert escape_string("\f") == r'"\f"'
    assert escape_string("\n") == r'"\n"'
    assert escape_string("\r") == r'"\r"'
    assert escape_string("\t") == r'"\t"'

    # Other control chars U+0000 through U+001F: must use \u00xx lowercase hex
    assert escape_string("\x00") == r'"\u0000"'
    assert escape_string("\x01") == r'"\u0001"'
    assert escape_string("\x1f") == r'"\u001f"'

    # Solidus '/' MUST NOT be escaped
    assert escape_string("https://auren.ai/path/to/resource") == '"https://auren.ai/path/to/resource"'

    # Printable UTF-8 preserved raw without ASCII escape
    assert escape_string("Hello, 世界! 🌍") == '"Hello, 世界! 🌍"'


def test_rejection_of_nan_infinity_and_non_serializable():
    """Validates that NaN, Infinity, and invalid types are strictly rejected."""
    with pytest.raises(ValueError, match="NaN and Infinity are not permitted"):
        canonicalize(float("nan"))

    with pytest.raises(ValueError, match="NaN and Infinity are not permitted"):
        canonicalize(float("inf"))

    with pytest.raises(ValueError, match="NaN and Infinity are not permitted"):
        canonicalize(float("-inf"))

    with pytest.raises(TypeError, match="is not JSON serializable"):
        canonicalize(object())


def test_datetime_microsecond_precision_and_timezone_normalization():
    """Validates microsecond precision and timezone normalization to UTC."""
    user_id = uuid4()
    conv_id = uuid4()
    nonce = uuid4()

    # Two timestamps representing the exact same instant with different timezone offsets
    # 2026-11-16 12:34:56.789012 UTC
    dt_utc = datetime(2026, 11, 16, 12, 34, 56, 789012, tzinfo=timezone.utc)
    # Same instant in UTC+2 (14:34:56.789012 +02:00)
    tz_plus_2 = timezone(timedelta(hours=2))
    dt_plus_2 = datetime(2026, 11, 16, 14, 34, 56, 789012, tzinfo=tz_plus_2)

    p1 = JournalConsentPayload(
        user_id=user_id,
        conversation_id=conv_id,
        idempotency_key="key-123",
        scope="journal.read",
        date_range="2026-11-01..2026-11-15",
        nonce=nonce,
        expires_at=dt_utc,
    )
    p2 = JournalConsentPayload(
        user_id=user_id,
        conversation_id=conv_id,
        idempotency_key="key-123",
        scope="journal.read",
        date_range="2026-11-01..2026-11-15",
        nonce=nonce,
        expires_at=dt_plus_2,
    )

    bytes1 = serialize_canonical_payload(p1)
    bytes2 = serialize_canonical_payload(p2)

    assert bytes1 == bytes2, "Timezone offsets for the same instant must serialize to identical canonical bytes"
    assert b"2026-11-16T12:34:56.789012Z" in bytes1, "Microsecond precision must be fully preserved"

    # Zero microseconds test
    dt_zero_micro = datetime(2026, 11, 16, 12, 0, 0, 0, tzinfo=timezone.utc)
    p_zero = JournalConsentPayload(
        user_id=user_id,
        conversation_id=conv_id,
        idempotency_key="key-123",
        scope="journal.read",
        date_range="2026-11-01..2026-11-15",
        nonce=nonce,
        expires_at=dt_zero_micro,
    )
    bytes_zero = serialize_canonical_payload(p_zero)
    assert b"2026-11-16T12:00:00Z" in bytes_zero


def test_rejection_of_naive_datetimes():
    """Validates that naive datetimes without timezone are strictly rejected."""
    naive_dt = datetime(2026, 11, 16, 12, 0, 0)
    with pytest.raises(ValueError, match="must be a timezone-aware datetime"):
        JournalConsentPayload(
            user_id=uuid4(),
            conversation_id=uuid4(),
            idempotency_key="key-123",
            scope="journal.read",
            date_range="2026-11-01..2026-11-15",
            nonce=uuid4(),
            expires_at=naive_dt,
        )


def test_journal_consent_token_signing_verification_parity(valid_hmac_secret):
    """Verifies that create_journal_consent_token and verify_journal_consent_token have 100% parity."""
    user_id = uuid4()
    conv_id = uuid4()
    nonce = uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)

    token = create_journal_consent_token(
        user_id=user_id,
        conversation_id=conv_id,
        idempotency_key="key-abc",
        scope="journal.read",
        date_range="2026-11-01..2026-11-15",
        nonce=nonce,
        expires_at=expires_at,
        secret=valid_hmac_secret,
    )

    # Verification must succeed
    assert verify_journal_consent_token(
        token=token,
        secret=valid_hmac_secret,
        expected_user_id=user_id,
        expected_conversation_id=conv_id,
        expected_idempotency_key="key-abc",
        expected_date_range="2026-11-01..2026-11-15",
        now=now,
    ) is True


def test_tampered_payload_rejected(valid_hmac_secret):
    """Verifies that modifying any field in a consent token causes verification to fail."""
    user_id = uuid4()
    conv_id = uuid4()
    nonce = uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)

    token = create_journal_consent_token(
        user_id=user_id,
        conversation_id=conv_id,
        idempotency_key="key-abc",
        scope="journal.read",
        date_range="2026-11-01..2026-11-15",
        nonce=nonce,
        expires_at=expires_at,
        secret=valid_hmac_secret,
    )

    # 1. Invalid signature
    tampered_sig_token = JournalConsentToken(
        payload=token.payload,
        signature="0" * 64,
    )
    with pytest.raises(InvalidSignatureError, match="signature is invalid"):
        verify_journal_consent_token(
            token=tampered_sig_token,
            secret=valid_hmac_secret,
            expected_user_id=user_id,
            expected_conversation_id=conv_id,
            expected_idempotency_key="key-abc",
            expected_date_range="2026-11-01..2026-11-15",
            now=now,
        )

    # 2. User ID mismatch
    with pytest.raises(ConsentUserMismatchError, match="does not match expected"):
        verify_journal_consent_token(
            token=token,
            secret=valid_hmac_secret,
            expected_user_id=uuid4(),
            expected_conversation_id=conv_id,
            expected_idempotency_key="key-abc",
            expected_date_range="2026-11-01..2026-11-15",
            now=now,
        )

    # 3. Conversation ID mismatch
    with pytest.raises(ConsentConversationMismatchError, match="does not match expected"):
        verify_journal_consent_token(
            token=token,
            secret=valid_hmac_secret,
            expected_user_id=user_id,
            expected_conversation_id=uuid4(),
            expected_idempotency_key="key-abc",
            expected_date_range="2026-11-01..2026-11-15",
            now=now,
        )

    # 4. Idempotency key mismatch
    with pytest.raises(ConsentIdempotencyMismatchError, match="idempotency_key mismatch"):
        verify_journal_consent_token(
            token=token,
            secret=valid_hmac_secret,
            expected_user_id=user_id,
            expected_conversation_id=conv_id,
            expected_idempotency_key="different-key",
            expected_date_range="2026-11-01..2026-11-15",
            now=now,
        )

    # 5. Date range mismatch
    with pytest.raises(DateRangeMismatchError, match="does not match requested"):
        verify_journal_consent_token(
            token=token,
            secret=valid_hmac_secret,
            expected_user_id=user_id,
            expected_conversation_id=conv_id,
            expected_idempotency_key="key-abc",
            expected_date_range="2026-10-01..2026-10-15",
            now=now,
        )

    # 6. Expired token
    future_now = now + timedelta(minutes=10)
    with pytest.raises(ExpiredConsentTokenError, match="has expired"):
        verify_journal_consent_token(
            token=token,
            secret=valid_hmac_secret,
            expected_user_id=user_id,
            expected_conversation_id=conv_id,
            expected_idempotency_key="key-abc",
            expected_date_range="2026-11-01..2026-11-15",
            now=future_now,
        )

    # 7. Excessive lifetime (over 15 minutes)
    long_expiry = now + timedelta(minutes=20)
    long_token = create_journal_consent_token(
        user_id=user_id,
        conversation_id=conv_id,
        idempotency_key="key-abc",
        scope="journal.read",
        date_range="2026-11-01..2026-11-15",
        nonce=uuid4(),
        expires_at=long_expiry,
        secret=valid_hmac_secret,
    )
    with pytest.raises(ExcessiveLifetimeError, match="exceeds maximum permitted window"):
        verify_journal_consent_token(
            token=long_token,
            secret=valid_hmac_secret,
            expected_user_id=user_id,
            expected_conversation_id=conv_id,
            expected_idempotency_key="key-abc",
            expected_date_range="2026-11-01..2026-11-15",
            now=now,
        )
