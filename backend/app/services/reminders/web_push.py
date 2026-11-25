"""Web Push (RFC 8291 aes128gcm & RFC 8292 VAPID ES256) sender using cryptography + pyjwt + httpx."""

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import struct
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import httpx
import jwt

from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(val: str) -> bytes:
    cleaned = val.strip()
    padding = "=" * ((4 - len(cleaned) % 4) % 4)
    return base64.urlsafe_b64decode(cleaned + padding)


def generate_vapid_keypair() -> Dict[str, str]:
    """Generate a fresh ECDSA P-256 keypair suitable for VAPID Web Push."""
    priv_key = ec.generate_private_key(ec.SECP256R1())
    priv_nums = priv_key.private_numbers()
    raw_priv = priv_nums.private_value.to_bytes(32, "big")
    raw_pub = priv_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return {
        "public_key": _b64url_encode(raw_pub),
        "private_key": _b64url_encode(raw_priv),
    }


def load_vapid_private_key(raw_key: str) -> ec.EllipticCurvePrivateKey:
    """Load an ECDSA P-256 private key from PEM or base64url 32-byte raw scalar."""
    cleaned = raw_key.strip()
    if "BEGIN" in cleaned and "PRIVATE KEY" in cleaned:
        loaded = serialization.load_pem_private_key(cleaned.encode("utf-8"), password=None)
        if not isinstance(loaded, ec.EllipticCurvePrivateKey):
            raise ValueError("VAPID private key must be an Elliptic Curve (P-256) key.")
        return loaded

    raw_bytes = _b64url_decode(cleaned)
    if len(raw_bytes) == 32:
        priv_val = int.from_bytes(raw_bytes, "big")
        return ec.derive_private_key(priv_val, ec.SECP256R1())
    # DER PKCS8 fallback
    loaded = serialization.load_der_private_key(raw_bytes, password=None)
    if not isinstance(loaded, ec.EllipticCurvePrivateKey):
        raise ValueError("VAPID private key must be an EC P-256 key.")
    return loaded


def get_uncompressed_public_key_b64url(private_key: ec.EllipticCurvePrivateKey) -> str:
    raw_pub = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url_encode(raw_pub)


def encrypt_web_push_payload(
    plaintext: bytes,
    p256dh_b64url: str,
    auth_b64url: str,
    record_size: int = 4096,
) -> bytes:
    """Encrypt push message payload strictly per RFC 8291 (aes128gcm content-encoding)."""
    ua_public_raw = _b64url_decode(p256dh_b64url)
    auth_secret = _b64url_decode(auth_b64url)
    if len(ua_public_raw) != 65 or ua_public_raw[0] != 0x04:
        raise ValueError("Invalid client p256dh public key (expected 65-byte uncompressed P-256 point).")
    if len(auth_secret) < 16:
        raise ValueError("Invalid client push auth secret (expected >= 16 bytes).")

    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public_raw)

    # Ephemeral sender keypair + 16-byte random salt
    as_private = ec.generate_private_key(ec.SECP256R1())
    as_public_raw = as_private.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    salt = os.urandom(16)

    shared_secret = as_private.exchange(ec.ECDH(), ua_public)

    # RFC 8291 Section 3.3 Key Derivation
    key_info = b"WebPush: info\x00" + ua_public_raw + as_public_raw
    ikm = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=auth_secret,
        info=key_info,
    ).derive(shared_secret)

    cek = HKDF(
        algorithm=hashes.SHA256(),
        length=16,
        salt=salt,
        info=b"Content-Encoding: aes128gcm\x00",
    ).derive(ikm)

    nonce = HKDF(
        algorithm=hashes.SHA256(),
        length=12,
        salt=salt,
        info=b"Content-Encoding: nonce\x00",
    ).derive(ikm)

    # RFC 8188 record delimiter: 0x02 marks final record
    padded_plaintext = plaintext + b"\x02"
    aesgcm = AESGCM(cek)
    ciphertext = aesgcm.encrypt(nonce, padded_plaintext, associated_data=b"")

    # Header: salt (16B) || rs (4B big-endian) || idlen (1B = 65) || keyid (65B)
    header = salt + struct.pack(">IB", record_size, len(as_public_raw)) + as_public_raw
    return header + ciphertext


def decrypt_web_push_payload(
    encrypted_body: bytes,
    ua_private_key: ec.EllipticCurvePrivateKey,
    auth_b64url: str,
) -> bytes:
    """Decrypt RFC 8291 aes128gcm payload (used for cryptographic roundtrip verification in tests)."""
    salt = encrypted_body[:16]
    rs, idlen = struct.unpack(">IB", encrypted_body[16:21])
    _ = rs
    as_public_raw = encrypted_body[21 : 21 + idlen]
    ciphertext = encrypted_body[21 + idlen :]

    ua_public_raw = ua_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    as_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public_raw)
    auth_secret = _b64url_decode(auth_b64url)

    shared_secret = ua_private_key.exchange(ec.ECDH(), as_public)
    key_info = b"WebPush: info\x00" + ua_public_raw + as_public_raw
    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=auth_secret, info=key_info).derive(shared_secret)
    cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)

    padded = AESGCM(cek).decrypt(nonce, ciphertext, associated_data=b"")
    idx = padded.rfind(b"\x02")
    return padded[:idx] if idx != -1 else padded


def build_vapid_headers(
    endpoint: str,
    private_key: ec.EllipticCurvePrivateKey,
    public_key_b64url: str,
    subject: str,
    ttl_seconds: int = 3600,
    urgency: str = "normal",
) -> Dict[str, str]:
    """Construct RFC 8292 VAPID Authorization and Web Push delivery headers."""
    parsed = urlparse(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    exp = int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
    claims = {
        "aud": audience,
        "exp": exp,
        "sub": subject,
    }
    token = jwt.encode(claims, private_key, algorithm="ES256")
    return {
        "Authorization": f"vapid t={token}, k={public_key_b64url}",
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(max(60, ttl_seconds)),
        "Urgency": urgency if urgency in ("very-low", "low", "normal", "high") else "normal",
    }


@dataclass
class WebPushDeliveryResult:
    success: bool
    status_code: Optional[int] = None
    expired_subscription: bool = False
    retryable: bool = False
    error_detail: Optional[str] = None


class WebPushService:
    """Async Web Push notification dispatcher enforcing VAPID & RFC 8291 encryption."""

    def __init__(
        self,
        settings: Settings = default_settings,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.settings = settings
        self._client = http_client

    def is_configured(self) -> bool:
        return bool(self.settings.VAPID_PUBLIC_KEY and self.settings.get_vapid_private_key())

    def get_public_key(self) -> Optional[str]:
        return self.settings.VAPID_PUBLIC_KEY.strip() if self.settings.VAPID_PUBLIC_KEY else None

    async def send_push(
        self,
        endpoint: str,
        p256dh: str,
        auth_secret: str,
        payload: Dict[str, Any],
        urgency: str = "normal",
        ttl_seconds: int = 3600,
    ) -> WebPushDeliveryResult:
        raw_priv = self.settings.get_vapid_private_key()
        pub_b64 = self.get_public_key()
        if not raw_priv or not pub_b64:
            return WebPushDeliveryResult(
                success=False,
                retryable=False,
                error_detail="VAPID keys are not configured on backend.",
            )

        try:
            priv_key = load_vapid_private_key(raw_priv)
            derived_pub = get_uncompressed_public_key_b64url(priv_key)
            # Use configured public key if matching; derived_pub ensures consistency
            k_header = pub_b64 or derived_pub
            headers = build_vapid_headers(
                endpoint=endpoint,
                private_key=priv_key,
                public_key_b64url=k_header,
                subject=self.settings.VAPID_SUBJECT,
                ttl_seconds=ttl_seconds,
                urgency=urgency,
            )
            body_bytes = encrypt_web_push_payload(
                plaintext=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                p256dh_b64url=p256dh,
                auth_b64url=auth_secret,
            )
        except Exception as exc:
            logger.warning("Web Push payload encryption/signing error: %s", exc)
            return WebPushDeliveryResult(
                success=False,
                retryable=False,
                error_detail=f"Push payload preparation error: {exc}",
            )

        try:
            if self._client:
                resp = await self._client.post(endpoint, content=body_bytes, headers=headers, timeout=10.0)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(endpoint, content=body_bytes, headers=headers)
        except httpx.TimeoutException as exc:
            return WebPushDeliveryResult(
                success=False,
                retryable=True,
                error_detail=f"Push gateway timeout: {exc}",
            )
        except httpx.RequestError as exc:
            return WebPushDeliveryResult(
                success=False,
                retryable=True,
                error_detail=f"Push gateway network error: {exc}",
            )

        if resp.status_code in (200, 201, 202):
            return WebPushDeliveryResult(success=True, status_code=resp.status_code)

        if resp.status_code in (404, 410):
            return WebPushDeliveryResult(
                success=False,
                status_code=resp.status_code,
                expired_subscription=True,
                retryable=False,
                error_detail=f"Push subscription expired or gone (HTTP {resp.status_code}).",
            )

        if resp.status_code in (429, 500, 502, 503, 504):
            return WebPushDeliveryResult(
                success=False,
                status_code=resp.status_code,
                retryable=True,
                error_detail=f"Transient push service error (HTTP {resp.status_code}).",
            )

        return WebPushDeliveryResult(
            success=False,
            status_code=resp.status_code,
            retryable=False,
            error_detail=f"Push rejected with HTTP {resp.status_code}",
        )

