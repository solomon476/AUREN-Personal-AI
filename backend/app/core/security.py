"""Security and authentication utilities for Supabase JWT verification."""

import logging
from typing import Optional
from uuid import UUID

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.models.user import AuthenticatedUser

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)

# Optional JWKS client cached at module level
_jwks_client: Optional[PyJWKClient] = None


def get_jwks_client() -> Optional[PyJWKClient]:
    """Retrieve or initialize the JWKS client for asymmetric JWT validation."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client

    jwks_url = settings.SUPABASE_JWKS_URL
    if not jwks_url and settings.SUPABASE_URL:
        jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"

    if jwks_url:
        try:
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=16)
        except Exception as exc:
            logger.warning("Could not initialize JWKS client from %s: %s", jwks_url, exc)
            _jwks_client = None

    return _jwks_client


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency to validate a Supabase JWT and return the authenticated user context.

    Enforces:
    - Token presence in the Authorization header (Bearer <token>)
    - Signature verification using JWKS (ES256/RS256) or JWT secret (HS256)
    - Valid audience, expiration, and user ID (`sub`) claim
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = None

    # 1. Attempt verification with asymmetric JWKS if available
    jwks_client = get_jwks_client()
    if jwks_client:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
            )
        except jwt.PyJWTError as err:
            logger.debug("JWKS verification unsuccessful or key not found: %s", err)

    # 2. Fallback to symmetric HS256 secret verification if configured
    if payload is None and settings.SUPABASE_JWT_SECRET:
        try:
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError as err:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication token: {str(err)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # If verification failed or neither key source was configured
    if payload is None:
        if not settings.SUPABASE_JWT_SECRET and not jwks_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase authentication keys not configured on server.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user ID
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing subject claim ('sub').",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format in token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        id=user_uuid,
        email=payload.get("email"),
        role=payload.get("role", "authenticated"),
        app_metadata=payload.get("app_metadata", {}),
        user_metadata=payload.get("user_metadata", {}),
    )

